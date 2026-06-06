# AGENTS.md - Plano tecnico do Devolu Nota

## Contexto

O Devolu Nota e um SaaS B2B para empresas emitirem e armazenarem notas de devolucao em lote.
O app deve operar com multi-tenant, usuarios por empresa, integracoes com marketplaces/ERPs,
emissao de notas, armazenamento fiscal, auditoria e retencao.

Este arquivo consolida os pontos levantados nos reviews de codigo e arquitetura.
Ele deve orientar os proximos agentes/desenvolvedores sobre o que melhorar e em qual ordem.

## Estado atual

- Backend: FastAPI, SQLAlchemy async, PostgreSQL, Alembic, Redis, Celery e APScheduler.
- Frontend: Next.js, React, TypeScript e chamadas para API.
- Docker Compose: `postgres`, `redis`, `backend`, `worker`, `scheduler`, `frontend`.
- Backend organizado em:
  - `routes`: HTTP.
  - `schemas`: contratos Pydantic.
  - `services`: regra de negocio.
  - `repositories`: persistencia.
  - `models`: entidades SQLAlchemy.
  - `integrations`: mocks externos.
  - `workers`: tarefas Celery.
## Principios obrigatorios

- Responder e documentar em portugues do Brasil.
- Manter monolito modular; nao criar microservicos agora.
- Nao implementar estoque.
- Nao colocar regra fiscal no frontend.
- Nao colocar regra de negocio pesada em rotas.
- Nao vazar tokens, senhas, credenciais ou conteudo fiscal bruto em logs.
- Sempre validar isolamento por `company_id`.
- Sempre adicionar testes quando mudar permissao, storage, retencao, auditoria ou jobs.
- Usar adapters/gateways para integracoes externas e storage.

## Arquitetura alvo

Manter o backend como monolito modular:

- `api/routes`: HTTP, dependencias e traducao de erros.
- `schemas`: entrada e saida publica da API.
- `services`: autorizacao, regras e transicoes de status.
- `repositories`: queries e persistencia.
- `models`: tabelas e constraints.
- `integrations`: Tiny, Mercado Livre, Shopee e mocks.
- `storage`: novo boundary para documentos fiscais.
- `workers`: tarefas lentas e retryable.
- `jobs`: agendamento recorrente.

Fluxo alvo:

1. Marketplace/ERP sincroniza devolucoes.
2. Backend cria ou atualiza `ReturnOrder`.
3. Usuario gera `ReturnNote`.
4. Usuario cria lote de emissao.
5. Worker processa `EmissionBatch` e `EmissionJob`.
6. Documento fiscal e salvo via `StorageProvider`.
7. Banco registra `FiscalDocument` e `StorageArchive`.
8. Retencao usa `retention_until`.
9. Auditoria registra transicoes relevantes.

## Prioridade 1 - Autorizacao por role

Problema:

- Hoje o app valida se o usuario pertence a empresa, mas nao aplica permissoes por role.
- Roles existentes: `OWNER`, `ADMIN`, `OPERATOR`, `VIEWER`.
- Acoes sensiveis podem ser executadas por qualquer membro ativo.

Objetivo:

- Criar politica central de autorizacao por empresa.
- Garantir que cada endpoint sensivel exija role correta.

Implementacao:

- Criar `CompanyPermissionService` ou helper equivalente.
- Implementar `require_company_role(company_id, current_user, allowed_roles)`.
- Validar usuario ativo, empresa acessivel, membership ativo e role permitida.

Politica sugerida:

- `OWNER`: todas as acoes.
- `ADMIN`: integracoes, credenciais, emissao, retencao e operacao.
- `OPERATOR`: sincronizar devolucoes, criar notas e emitir lotes.
- `VIEWER`: somente leitura.

Endpoints prioritarios:

- Usuarios da empresa.
- Integracoes e credenciais.
- Emissao em lote.
- Documentos fiscais.
- Retencao.

Testes:

- `VIEWER` nao executa mutacao.
- `OPERATOR` nao altera credenciais nem roda retencao.
- `ADMIN` roda retencao e configura integracao.
- Usuario de outra empresa nao acessa dados por id direto.
- Membership inativo nao acessa empresa.

## Prioridade 2 - Storage fiscal local real

Problema:

- O servico fiscal calcula checksum e tamanho, mas nao salva o conteudo.
- O banco registra metadados como se o documento estivesse armazenado.
- Nao da para recuperar XML/DANFE/JSON nem validar integridade.

Objetivo:

- Criar boundary de storage real, mesmo que local/mock.
- Permitir salvar, ler e validar documentos fiscais.

Implementacao:

- Criar `backend/app/storage`.
- Criar interface:
  - `save_object(bucket, object_key, content_bytes, content_type)`.
  - `read_object(bucket, object_key)`.
  - `object_exists(bucket, object_key)`.
- Criar `LocalStorageProvider`.
- Salvar em path ignorado pelo git, por exemplo:
  - `backend/.local-storage/{bucket}/{object_key}`.
- O servico fiscal deve:
  - receber conteudo;
  - gerar checksum;
  - salvar bytes;
  - persistir `StorageArchive`;
  - persistir `FiscalDocument`;
  - validar checksum apos salvar.

Cuidados:

- Nao logar conteudo fiscal.
- Normalizar `object_key` contra path traversal.
- Incluir `company_id` no caminho do objeto.
- Nao expor arquivo sem permissao.

Testes:

- Salvar documento cria arquivo local.
- Ler documento retorna bytes originais.
- Checksum salvo bate com conteudo.
- Cross-tenant nao acessa documento.
- Documento inexistente retorna erro correto.

## Prioridade 3 - Retencao por `retention_until`

Problema:

- A retencao usa `StorageArchive.created_at`.
- Existe `retention_until`, mas ele ainda nao guia a politica.
- Documento antigo importado hoje pode receber prazo errado.

Objetivo:

- Calcular e persistir data correta de retencao.
- Usar `retention_until` na retencao.

Implementacao:

- Ao armazenar documento, calcular `retention_until`.
- Base preferida:
  - `FiscalDocument.issued_at`;
  - data fiscal extraida do documento/chave;
  - fallback controlado para mock.
- Repositorio de retencao deve buscar por `retention_until`.
- Jobs devem registrar acao aplicada.
- Evitar `365 * anos` se a regra exigir ano calendario.

Testes:

- Documento de 6 anos vai para `COLD`.
- Documento de 12 anos vai para `DELETED`.
- Documento antigo importado hoje segue data fiscal antiga.
- Documento recente nao e afetado.
- Rodar retencao duas vezes nao duplica efeito.

## Prioridade 4 - Auditoria forte

Problema:

- Auditoria existe, mas alguns eventos tem pouco contexto.
- Retencao precisa ser rastreavel.

Objetivo:

- Tornar logs uteis para suporte, investigacao e demo.

Melhorias:

- Registrar `previous_status`, `new_status`, `reason`, ids relacionados e politica aplicada.
- Em retencao, registrar:
  - acao aplicada;
  - cutoff;
  - `retention_until`;
  - archive afetado;
  - documentos afetados;
  - status anterior e novo.
- Nunca registrar credenciais ou conteudo fiscal bruto.

Testes:

- Logs nao contem tokens/senhas.
- Retencao registra politica e transicao.
- Logs de uma empresa nao aparecem para outra.

## Prioridade 5 - Scheduler e jobs reais

Problema:

- O projeto ja tem `worker` e `scheduler`.
- Scheduler ainda e heartbeat.
- Emissao mockada usa worker, mas o ciclo de jobs precisa amadurecer.

Objetivo:

- Usar background jobs para tarefas lentas, recorrentes e retryable.

Implementacao:

- Scheduler deve disparar retencao periodica.
- Worker deve processar emissao, sincronizacoes futuras, retencao e revalidacao de integracoes.
- Jobs devem ter status, tentativas, erro, timestamps e idempotencia.

Testes:

- Job nao processa lote finalizado duas vezes.
- Retry nao duplica nota.
- Falha externa deixa status rastreavel.
- Scheduler chama tarefa sem rota HTTP.

## Prioridade 6 - Sessao frontend

Problema:

- Tokens ficam em `localStorage`.
- Para MVP local funciona, mas nao e ideal para producao.

Objetivo:

- Reduzir risco de roubo de token via XSS.

- Migrar refresh token para cookie HTTP-only.
- Manter access token curto.
- Implementar refresh silencioso.
- Invalidar sessao no logout.

## Prioridade 7 - Polimento para demo

Problema:

- Algumas telas ainda usam termos de sessao/mock.
- Estados de loading, vazio e erro ainda parecem prototipo.

Melhorias:

- Trocar textos como "da sessao" por "da empresa" ou "persistidas".
- Padronizar loading, empty state e error state.
- Mostrar progresso de jobs.
- Criar visao de documentos fiscais armazenados.
- Criar acao/tela de retencao apenas para admin.

## Ordem recomendada

1. Autorizacao por role.
2. Storage fiscal local real.
3. Retencao por `retention_until`.
4. Auditoria mais completa.
5. Scheduler com tarefas reais.
6. Seguranca de sessao.
7. Polimento frontend.

## Pronto para demo tecnica

- Role errada nao executa acao sensivel.
- Documento fiscal mockado e salvo em storage local.
- Checksum pode ser verificado.
- Retencao usa `retention_until`.
- Auditoria mostra eventos importantes sem dados sensiveis.
- Testes, lint e build passam.
- Docker Compose sobe sem erro.
- Fluxo basico funciona em `localhost:3000/app`.

## Pronto para cliente real

- Autorizacao por role implementada e testada.
- Storage real ou local confiavel com recuperacao de documento.
- Retencao correta, auditavel e idempotente.
- Sessao frontend com estrategia segura.
- Jobs com retry e rastreabilidade.
- Logs sem informacao sensivel.
- Ambientes separados para dev, staging e producao.
- Health checks uteis para API, banco, Redis e worker.
- README atualizado com setup e fluxo de uso.
