# Notas de Devolucao SaaS

SaaS B2B web para automatizar, de forma incremental, o fluxo de Notas Fiscais de Entrada de Devolucao para lojistas que vendem em marketplaces como Mercado Livre e Shopee e usam o Tiny ERP.

Este README e a fonte principal de documentacao do projeto. O objetivo e manter aqui o estado real da aplicacao, os contratos ja implementados, as fronteiras de seguranca, os comandos de execucao e o roadmap tecnico sem duplicar informacao em documentos soltos.

## Visao Geral

O Notas de Devolucao SaaS nao e um sistema de estoque. Ele e uma base SaaS multi-tenant para identificar devolucoes, relacionar pedidos a notas fiscais originais, preparar notas de entrada de devolucao, emitir em lote no futuro, registrar historico, armazenar documentos fiscais e aplicar politica de retencao.

Principio central:

> Cada dado operacional pertence a uma empresa, e todo acesso deve passar por autenticacao e validacao de vinculo multi-tenant no backend.

O runtime atual inclui:

- backend FastAPI modular;
- frontend Next.js operacional inicial;
- PostgreSQL com Alembic;
- Redis preparado para filas;
- Celery worker preparado;
- APScheduler preparado;
- autenticacao JWT com access token e refresh token;
- hash de senha com bcrypt;
- criptografia autenticada de credenciais sensiveis com AES-GCM;
- autorizacao central por role de empresa;
- rotas multi-tenant para empresas, usuarios vinculados e integracoes;
- mocks isolados para Tiny, Mercado Livre e Shopee;
- sincronizacao mockada de devolucoes de marketplace;
- criacao mockada de nota fiscal de entrada de devolucao;
- lotes e jobs de emissao mockada;
- storage fiscal local para XML/DANFE mockados;
- listagem e download de documentos fiscais armazenados;
- politica de retencao baseada em `retention_until`;
- job recorrente de retencao via APScheduler;
- historico operacional em `audit_logs`;
- frontend autenticado minimo para operar o fluxo mockado;
- sanitizacao de erros de validacao para nao vazar payload sensivel;
- testes reais contra API e PostgreSQL local;
- Docker Compose para ambiente local completo.

Nao existe, nesta etapa:

- controle de estoque;
- balanceamento de estoque;
- integracao real com Tiny, Mercado Livre ou Shopee;
- emissao real de NF-e;
- regra fiscal definitiva;
- frontend completo de producao.

## Principais Funcionalidades

- **Autenticacao JWT**: registro, login, refresh token e endpoint `me`.
- **Senhas seguras**: senhas sao persistidas apenas como hash bcrypt.
- **Multi-tenant por empresa**: empresas sao acessadas somente por usuarios vinculados em `company_users`.
- **Autorizacao por role**: leitura, operacao e administracao usam politica central em `CompanyService`.
- **Criacao de empresa com OWNER automatico**: ao criar uma empresa, o usuario autenticado vira `OWNER`.
- **Vinculo de usuarios a empresas**: usuarios existentes podem ser vinculados com roles `OWNER`, `ADMIN`, `OPERATOR` ou `VIEWER`.
- **Integracoes por empresa**: cadastro, listagem, consulta e atualizacao de integracoes por `company_id`.
- **Credenciais criptografadas**: `access_token`, `refresh_token`, `api_token` e `client_secret` sao armazenados em `encrypted_credentials`.
- **Settings nao sensiveis**: `settings` rejeita campos sensiveis para evitar token em texto puro.
- **Mocks de integracao**: clients mockados de Tiny, Mercado Livre e Shopee validam fluxos antes das integracoes reais.
- **Sincronizacao mockada de devolucoes**: devolucoes de marketplace sao persistidas com idempotencia por empresa, marketplace e pedido externo.
- **Criacao mockada de nota de entrada**: o backend cruza devolucao com NF-e original simulada no Tiny e cria `return_notes` em `DRAFT`.
- **Emissao mockada em lote**: o backend cria `emission_batches`, cria `emission_jobs`, move notas para `QUEUED` e processa cenarios mockados de sucesso ou falha.
- **Documentos fiscais locais**: emissao mockada bem-sucedida gera XML e DANFE mockados, salva bytes em storage local e registra checksum.
- **Download seguro de documentos**: documentos fiscais sao listados e baixados somente por usuarios vinculados a empresa.
- **Retencao fiscal**: archives usam `retention_until`, podem ir para `COLD` ou `DELETED` e geram auditoria.
- **Scheduler de retencao**: APScheduler roda ciclo periodico por empresas ativas e registra `retention_jobs`.
- **Historico operacional**: eventos de emissao mockada sao registrados em `audit_logs` e expostos por rota multi-tenant.
- **Frontend autenticado minimo**: login, cadastro, empresas, conexoes, devolucoes, emissoes e historico consomem a API existente.
- **Erros 422 sanitizados**: payloads invalidos nao retornam `input` nem valores sensiveis.
- **Alembic versionado**: schema relacional criado e evoluido por migrations.
- **Testes de contrato e seguranca**: cobrem autenticacao, tenant boundary, criptografia, rotas e metadata dos models.

## Fluxo de Arquitetura

```mermaid
flowchart TD
  A["Frontend Next.js"] --> B["FastAPI"]
  B --> C["Routes /api/v1"]
  C --> D["Dependencies: JWT + current_user"]
  D --> E["Services"]
  E --> F["Repositories"]
  F --> G["SQLAlchemy Models"]
  G --> H["PostgreSQL"]
  E --> I["Encryption Service AES-GCM"]
  B --> J["Redis"]
  J --> K["Celery Worker"]
  B --> L["APScheduler"]
  M["Alembic"] --> H
```

## Fluxo de Execucao Atual

1. Usuario cria conta em `POST /api/v1/auth/register`.
2. Backend salva `users.password_hash` usando bcrypt.
3. Backend retorna access token e refresh token JWT.
4. Usuario cria empresa em `POST /api/v1/companies`.
5. Backend cria `companies` e vincula o usuario em `company_users` como `OWNER`.
6. Usuario lista e consulta apenas empresas onde tem vinculo ativo.
7. Usuario vincula outros usuarios existentes a empresa.
8. Usuario cria integracao em `POST /api/v1/companies/{company_id}/integrations`.
9. Se houver credenciais, backend criptografa antes de persistir.
10. Usuario sincroniza devolucoes mockadas em `POST /api/v1/companies/{company_id}/return-orders/mock-sync`.
11. Backend persiste devolucoes com isolamento por empresa e idempotencia.
12. Usuario cria nota de entrada mockada em `POST /api/v1/companies/{company_id}/return-orders/{return_order_id}/return-notes/mock`.
13. Backend busca a NF-e original simulada no Tiny mock, cria `return_notes` em `DRAFT` e vincula o pedido a `LINKED_TO_NFE`.
14. Usuario cria lote de emissao mockada em `POST /api/v1/companies/{company_id}/emission-batches/mock`.
15. Backend cria um job por nota, move as notas para `QUEUED` e permite processamento mockado via service/task Celery.
16. Processamento mockado bem-sucedido marca nota como `ISSUED`, cria chave de devolucao mockada e armazena XML/DANFE em storage local.
17. Usuario lista documentos em `GET /api/v1/companies/{company_id}/fiscal-documents` e baixa conteudo validado por checksum.
18. Admin aplica retencao manual em `POST /api/v1/companies/{company_id}/retention/apply`, ou o scheduler executa o ciclo recorrente.
19. Backend registra eventos operacionais em `audit_logs`.
20. API publica nunca retorna `password_hash`, tokens ou `encrypted_credentials`.

## API

Base local do backend:

```http
http://localhost:8000
```

OpenAPI:

```http
GET http://localhost:8000/api/v1/openapi.json
GET http://localhost:8000/docs
```

### Health

```http
GET /health
```

Resposta:

```json
{
  "status": "ok",
  "service": "api"
}
```

### Auth

#### Registrar usuario

```http
POST /api/v1/auth/register
Content-Type: application/json
```

```json
{
  "email": "lojista@example.com",
  "name": "Lojista Exemplo",
  "password": "strong-pass"
}
```

Resposta:

```json
{
  "access_token": "jwt-access-token",
  "refresh_token": "jwt-refresh-token",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### Login

```http
POST /api/v1/auth/login
Content-Type: application/json
```

```json
{
  "email": "lojista@example.com",
  "password": "strong-pass"
}
```

#### Refresh

```http
POST /api/v1/auth/refresh
Content-Type: application/json
```

```json
{
  "refresh_token": "jwt-refresh-token"
}
```

#### Usuario autenticado

```http
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

Resposta publica:

```json
{
  "id": "uuid",
  "email": "lojista@example.com",
  "name": "Lojista Exemplo",
  "status": "ACTIVE",
  "created_at": "2026-06-04T00:00:00"
}
```

### Empresas

Todas as rotas exigem access token.

#### Criar empresa

```http
POST /api/v1/companies
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "legal_name": "Empresa Exemplo LTDA",
  "trade_name": "Loja Exemplo",
  "document": "12345678000199"
}
```

Ao criar a empresa, o usuario autenticado e vinculado como `OWNER`.

#### Listar empresas acessiveis

```http
GET /api/v1/companies
Authorization: Bearer <access_token>
```

#### Consultar empresa

```http
GET /api/v1/companies/{company_id}
Authorization: Bearer <access_token>
```

Se o usuario nao tiver vinculo ativo com a empresa, a API retorna `404`.

#### Listar usuarios da empresa

```http
GET /api/v1/companies/{company_id}/users
Authorization: Bearer <access_token>
```

#### Vincular usuario existente

```http
POST /api/v1/companies/{company_id}/users
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "user_id": "uuid-do-usuario",
  "role": "OPERATOR"
}
```

Roles aceitos:

- `OWNER`
- `ADMIN`
- `OPERATOR`
- `VIEWER`

### Integracoes

As rotas de integracoes tambem sao multi-tenant e ficam aninhadas em empresa.

#### Criar integracao

```http
POST /api/v1/companies/{company_id}/integrations
Authorization: Bearer <access_token>
Content-Type: application/json
```

Sem credenciais:

```json
{
  "provider": "TINY",
  "settings": {
    "sync_interval_minutes": 30
  }
}
```

Com credenciais:

```json
{
  "provider": "TINY",
  "settings": {
    "sync_interval_minutes": 30
  },
  "credentials": {
    "api_token": "token-do-tiny"
  }
}
```

Providers aceitos:

- `TINY`
- `MERCADO_LIVRE`
- `SHOPEE`

Campos sensiveis aceitos apenas em `credentials`:

- `access_token`
- `refresh_token`
- `api_token`
- `client_secret`

Campos sensiveis sao rejeitados em `settings`.

#### Listar integracoes

```http
GET /api/v1/companies/{company_id}/integrations
Authorization: Bearer <access_token>
```

#### Consultar integracao

```http
GET /api/v1/companies/{company_id}/integrations/{integration_id}
Authorization: Bearer <access_token>
```

#### Atualizar status/settings

```http
PATCH /api/v1/companies/{company_id}/integrations/{integration_id}
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "status": "ERROR",
  "settings": {
    "sync_interval_minutes": 60
  }
}
```

Status aceitos:

- `ACTIVE`
- `INVALID_TOKEN`
- `EXPIRED`
- `DISCONNECTED`
- `ERROR`

#### Substituir credenciais

```http
PUT /api/v1/companies/{company_id}/integrations/{integration_id}/credentials
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "access_token": "novo-access-token",
  "refresh_token": "novo-refresh-token"
}
```

Resposta publica de integracao:

```json
{
  "id": "uuid",
  "company_id": "uuid",
  "provider": "TINY",
  "status": "ACTIVE",
  "settings": {
    "sync_interval_minutes": 30
  },
  "last_sync_at": null,
  "created_at": "2026-06-04T00:00:00",
  "updated_at": "2026-06-04T00:00:00"
}
```

Campos proibidos na resposta:

- `password_hash`
- `encrypted_credentials`
- `access_token`
- `refresh_token`
- `api_token`
- `client_secret`

### Devolucoes Mockadas

As rotas de devolucoes mockadas sao multi-tenant, exigem access token e existem para validar o fluxo antes de integrar com APIs reais.

#### Sincronizar devolucoes mockadas

```http
POST /api/v1/companies/{company_id}/return-orders/mock-sync
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "marketplace": "MERCADO_LIVRE",
  "scenario": "success"
}
```

Marketplaces aceitos:

- `MERCADO_LIVRE`
- `SHOPEE`

Scenarios aceitos:

- `success`
- `invalid_token`
- `timeout`
- `external_error`

Resposta de sucesso:

```json
{
  "company_id": "uuid",
  "marketplace": "MERCADO_LIVRE",
  "created": 1,
  "updated": 0,
  "skipped": 0,
  "items": [
    {
      "id": "uuid",
      "company_id": "uuid",
      "marketplace": "MERCADO_LIVRE",
      "external_order_id": "ML-RETURN-1001",
      "status": "OPEN",
      "original_nfe_key": null,
      "payload": {
        "status": "RETURNED"
      },
      "created_at": "2026-06-04T00:00:00",
      "updated_at": "2026-06-04T00:00:00"
    }
  ]
}
```

O sync e idempotente por `company_id`, `marketplace` e `external_order_id`. Se uma devolucao existente ja tiver `original_nfe_key`, a chave nao e sobrescrita pelo mock.

#### Criar nota de entrada mockada

```http
POST /api/v1/companies/{company_id}/return-orders/{return_order_id}/return-notes/mock
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "scenario": "success"
}
```

Resposta de sucesso:

```json
{
  "id": "uuid",
  "company_id": "uuid",
  "return_order_id": "uuid",
  "status": "DRAFT",
  "original_nfe_key": "35260612345678000199550010000010011000010010",
  "return_nfe_key": null,
  "number": null,
  "series": null,
  "issued_at": null,
  "error_message": null,
  "created_at": "2026-06-04T00:00:00",
  "updated_at": "2026-06-04T00:00:00"
}
```

A criacao mockada rejeita nota ativa duplicada para o mesmo pedido e atualiza o pedido de devolucao para `LINKED_TO_NFE`.

Erros controlados de provedor retornam `detail.code`, `detail.provider`, `detail.message` e `detail.retryable`, sem credenciais ou tokens.

ATENCAO: a montagem fiscal definitiva da nota de entrada precisa ser validada com contador ou especialista fiscal antes de uso em producao.

### Emissao Mockada em Lote

As rotas de emissao mockada validam o ciclo operacional de lote e jobs antes de qualquer emissao fiscal real.

#### Criar lote de emissao mockada

```http
POST /api/v1/companies/{company_id}/emission-batches/mock
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "return_note_ids": ["uuid-da-nota"],
  "scenario": "success"
}
```

Scenarios aceitos:

- `success`
- `partial_failure`
- `failure`

Regras principais:

- notas devem pertencer a empresa do usuario;
- notas devem estar em `DRAFT` ou `READY_TO_EMIT`;
- notas duplicadas na mesma requisicao sao rejeitadas;
- notas em lote ativo ou status nao elegivel sao rejeitadas;
- ao criar o lote, as notas entram em `QUEUED`;
- cada nota gera exatamente um `emission_job`.

Resposta de sucesso:

```json
{
  "id": "uuid",
  "company_id": "uuid",
  "requested_by_user_id": "uuid",
  "status": "PENDING",
  "started_at": null,
  "finished_at": null,
  "created_at": "2026-06-04T00:00:00",
  "updated_at": "2026-06-04T00:00:00",
  "jobs": [
    {
      "id": "uuid",
      "company_id": "uuid",
      "batch_id": "uuid",
      "return_note_id": "uuid",
      "status": "PENDING",
      "attempts": 0,
      "scheduled_at": null,
      "started_at": null,
      "finished_at": null,
      "last_error": null,
      "created_at": "2026-06-04T00:00:00",
      "updated_at": "2026-06-04T00:00:00"
    }
  ]
}
```

#### Consultar lote

```http
GET /api/v1/companies/{company_id}/emission-batches/{batch_id}
Authorization: Bearer <access_token>
```

#### Listar jobs do lote

```http
GET /api/v1/companies/{company_id}/emission-batches/{batch_id}/jobs
Authorization: Bearer <access_token>
```

#### Processamento mockado

O processamento e implementado em service isolado e exposto por wrapper Celery `emissions.process_mock_batch`.

Efeitos por scenario:

- `success`: lote `COMPLETED`, jobs `SUCCESS`, notas `ISSUED`, `return_nfe_key` mockada, `issued_at` preenchido, XML e DANFE mockados salvos no storage local.
- `failure`: lote `FAILED`, jobs `FAILED`, notas `FAILED` e mensagens de erro controladas.
- `partial_failure`: lote `FAILED`, mistura de jobs `SUCCESS` e `FAILED`.

Esta etapa nao emite NF-e real, nao chama Tiny real, nao chama SEFAZ e nao gera XML/DANFE real. Os arquivos salvos sao artefatos mockados para validar storage, checksum, download, auditoria e retencao.

### Documentos Fiscais

Documentos fiscais ficam aninhados por empresa e exigem access token. Todas as roles ativas da empresa podem consultar e baixar documentos; o backend sempre valida `company_id`.

#### Listar documentos fiscais

```http
GET /api/v1/companies/{company_id}/fiscal-documents
Authorization: Bearer <access_token>
```

Filtros opcionais:

- `return_note_id`
- `limit`, default `50`, maximo `100`
- `offset`, default `0`

Resposta:

```json
{
  "items": [
    {
      "id": "uuid",
      "company_id": "uuid",
      "return_note_id": "uuid",
      "document_type": "NFE_XML",
      "status": "PENDING",
      "access_key": "35260612345678000199550010000010011000010010",
      "xml_storage_archive_id": "uuid",
      "pdf_storage_archive_id": null,
      "issued_at": "2026-06-04T00:00:00",
      "cancelled_at": null,
      "created_at": "2026-06-04T00:00:00",
      "updated_at": "2026-06-04T00:00:00"
    }
  ],
  "limit": 50,
  "offset": 0
}
```

Tipos atualmente armazenados pelo fluxo mockado:

- `NFE_XML`
- `DANFE_PDF`

#### Baixar documento fiscal

```http
GET /api/v1/companies/{company_id}/fiscal-documents/{fiscal_document_id}/download
Authorization: Bearer <access_token>
```

O backend le o objeto no storage local, recalcula o SHA-256 e retorna `409` se o checksum nao bater. Recurso inexistente ou de outra empresa retorna `404`.

### Retencao

Retencao usa `storage_archives.retention_until` e exige role administrativa (`OWNER` ou `ADMIN`) quando acionada via API.

#### Aplicar retencao manual

```http
POST /api/v1/companies/{company_id}/retention/apply
Authorization: Bearer <access_token>
```

Resposta:

```json
{
  "moved_to_cold": 1,
  "moved_to_deleted": 0,
  "skipped": 0
}
```

Politica atual:

- `COLD`: archives ativos com `retention_until` vencido.
- `DELETED`: archives em `COLD` cujo `retention_until` venceu ha pelo menos mais 5 anos.
- parametros padrao: `cold_after_years = 5`, `delete_after_years = 10`.

Transicoes de retencao registram auditoria com status anterior, novo status, motivo, cutoff, `retention_until` e politica aplicada.

### Historico Operacional

Eventos relevantes da emissao mockada sao persistidos em `audit_logs` para rastreabilidade por empresa.

#### Listar audit logs da empresa

```http
GET /api/v1/companies/{company_id}/audit-logs
Authorization: Bearer <access_token>
```

Filtros opcionais:

- `entity_type`
- `entity_id`
- `action`
- `created_from`
- `created_to`
- `limit`, default `50`, maximo `100`
- `offset`, default `0`

Resposta:

```json
{
  "items": [
    {
      "id": "uuid",
      "company_id": "uuid",
      "user_id": "uuid",
      "action": "EMISSION_BATCH_CREATED",
      "entity_type": "emission_batch",
      "entity_id": "uuid",
      "metadata": {
        "status": "PENDING"
      },
      "created_at": "2026-06-04T00:00:00"
    }
  ],
  "limit": 50,
  "offset": 0
}
```

Eventos registrados:

- `EMISSION_BATCH_CREATED`
- `EMISSION_JOB_CREATED`
- `RETURN_NOTE_QUEUED`
- `EMISSION_BATCH_STARTED`
- `EMISSION_JOB_STARTED`
- `EMISSION_JOB_SUCCEEDED`
- `EMISSION_JOB_FAILED`
- `RETURN_NOTE_ISSUED`
- `RETURN_NOTE_FAILED`
- `EMISSION_BATCH_COMPLETED`
- `EMISSION_BATCH_FAILED`
- `STORAGE_ARCHIVE_MOVED_TO_COLD`
- `STORAGE_ARCHIVE_DELETED_BY_RETENTION`

Logs iniciados por rota autenticada preservam `user_id`. Logs do processamento assincrono podem ter `user_id` nulo. Metadata com chaves sensiveis como `access_token`, `refresh_token`, `api_token`, `client_secret`, `encrypted_credentials`, `password`, `password_hash` ou `secret` e rejeitada.

## Modelo de Dados

Tabelas principais ja modeladas:

- `companies`
- `users`
- `company_users`
- `integrations`
- `marketplace_accounts`
- `return_orders`
- `return_notes`
- `emission_batches`
- `emission_jobs`
- `fiscal_documents`
- `audit_logs`
- `storage_archives`
- `retention_jobs`

Indices relevantes foram criados para campos como:

- `company_id`
- `status`
- `created_at`
- `marketplace`
- `external_order_id`
- `original_nfe_key`
- `retention_until`

Constraints importantes:

- `companies.document` unico;
- `users.email` unico;
- `company_users.company_id + user_id` unico;
- `marketplace_accounts.company_id + marketplace + external_account_id` unico;
- `return_orders.company_id + marketplace + external_order_id` unico.

## Seguranca

Regras aplicadas:

- Senhas nunca sao salvas em texto puro.
- Tokens JWT usam `JWT_SECRET_KEY`.
- Credenciais externas usam `ENCRYPTION_KEY` e AES-GCM.
- Rotas sensiveis exigem access token.
- Refresh token nao autoriza rotas protegidas.
- Acesso multi-tenant e validado no backend.
- Mutacoes sensiveis usam roles da empresa:
  - `OWNER` e `ADMIN`: administracao, usuarios, integracoes, credenciais e retencao manual.
  - `OPERATOR`: operacoes como sync de devolucoes, criacao de notas e emissao mockada.
  - `VIEWER`: leitura.
- Erros 422 sao sanitizados para remover `input`, `ctx` e `url`.
- Credenciais nao aparecem em responses publicas.
- Conteudo fiscal bruto nao deve ser logado.

Variaveis sensiveis nunca devem ser commitadas com valores reais.

## Interface

O frontend fica em `frontend/` e usa Next.js.

Arquivos principais atuais:

- `frontend/app/login/page.tsx`: login;
- `frontend/app/register/page.tsx`: cadastro;
- `frontend/app/(protected)/app/page.tsx`: dashboard protegido;
- `frontend/app/(protected)/app/companies/page.tsx`: empresas e selecao de empresa ativa;
- `frontend/app/(protected)/app/integrations/page.tsx`: conexoes mockadas;
- `frontend/app/(protected)/app/returns/page.tsx`: sincronizacao de devolucoes e criacao de nota mockada;
- `frontend/app/(protected)/app/emissions/page.tsx`: criacao de lote de emissao mockada;
- `frontend/app/(protected)/app/documents/page.tsx`: listagem e download de XML/DANFE mockados;
- `frontend/app/(protected)/app/audit-logs/page.tsx`: historico operacional;
- `frontend/app/layout.tsx`: layout base;
- `frontend/app/globals.css`: estilos globais;
- `frontend/components/api-health-badge.tsx`: status da API.
- `frontend/components/auth-provider.tsx`: sessao local do MVP;
- `frontend/components/protected-layout.tsx`: layout protegido e navegacao;
- `frontend/services/api.ts`: client HTTP tipado.

O frontend atual permite operar o MVP mockado com `access_token` salvo no navegador. Esta decisao e pragmatica para desenvolvimento local; em producao, a sessao deve ser revisada para uma estrategia mais robusta.

Rotas do frontend:

```text
http://localhost:3000/login
http://localhost:3000/register
http://localhost:3000/app
http://localhost:3000/app/companies
http://localhost:3000/app/integrations
http://localhost:3000/app/returns
http://localhost:3000/app/emissions
http://localhost:3000/app/documents
http://localhost:3000/app/audit-logs
```

Fluxo manual recomendado:

1. Criar conta em `/register`.
2. Criar empresa em `/app/companies`.
3. Criar conexoes mockadas em `/app/integrations`.
4. Sincronizar devolucoes em `/app/returns`.
5. Criar nota mockada para uma devolucao.
6. Criar lote mockado em `/app/emissions`.
7. Processar o lote pelo worker/service mockado.
8. Baixar XML/DANFE mockados em `/app/documents`.
9. Ver eventos em `/app/audit-logs`.

## Estrutura de Pastas

```text
backend/
  alembic/
    env.py
    versions/
      20260604_0001_initial_domain_models.py
      20260604_0002_add_user_password_hash.py
      20260604_0003_add_integration_encrypted_credentials.py
  app/
    api/
      dependencies.py
      exception_handlers.py
      v1/
        routes/
          audit_logs.py
          auth.py
          companies.py
          fiscal_documents.py
          health.py
          integrations.py
          emission_batches.py
          retention.py
          return_orders.py
    core/
      config.py
      encryption.py
      security.py
    db/
      base.py
      session.py
    integrations/
      errors.py
      mock_scenarios.py
      mercado_livre/
        mock_client.py
      shopee/
        mock_client.py
      tiny/
        mock_client.py
    jobs/
      scheduler.py
    models/
      domain.py
    repositories/
      audit_logs.py
      companies.py
      integrations.py
      emissions.py
      fiscal_documents.py
      return_notes.py
      return_orders.py
      users.py
      retention.py
      retention_jobs.py
    schemas/
      audit_logs.py
      auth.py
      companies.py
      health.py
      integrations.py
      emissions.py
      fiscal_documents.py
      mock_integrations.py
      retention.py
      return_notes.py
      return_orders.py
    services/
      audit_logs.py
      auth.py
      companies.py
      integration_credentials.py
      integrations.py
      emissions.py
      fiscal_documents.py
      mock_integrations.py
      retention.py
      return_notes.py
      return_orders.py
    storage/
      local.py
    workers/
      celery_app.py
      tasks.py
  tests/
    test_auth.py
    test_audit_logs.py
    test_companies.py
    test_company_role_authorization.py
    test_domain_models.py
    test_encryption.py
    test_fiscal_documents_storage.py
    test_health.py
    test_integrations.py
    test_local_storage.py
    test_emission_batches_mock.py
    test_mock_integrations.py
    test_retention.py
    test_return_notes_mock_creation.py
    test_return_orders_mock_sync.py
    test_scheduler.py
  pyproject.toml

frontend/
  app/
    (protected)/
      app/
        audit-logs/
        companies/
        emissions/
        documents/
        integrations/
        returns/
    login/
    register/
    globals.css
    layout.tsx
    page.tsx
  components/
    api-health-badge.tsx
    auth-provider.tsx
    protected-layout.tsx
    ui.tsx
  hooks/
  services/
    api.ts
    ui-storage.ts
  types/
    api.ts
  package.json

docker-compose.yml
.env.example
README.md
```

## Como Rodar com Docker

Copie o arquivo de ambiente:

```bash
copy .env.example .env
```

Suba os servicos:

```bash
docker compose up -d
```

Servicos:

- backend: `http://localhost:8000`
- frontend: `http://localhost:3000`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

Aplicar migrations:

```bash
docker compose exec backend alembic upgrade head
```

Verificar API:

```bash
curl http://localhost:8000/health
```

Rodar testes no container:

```bash
docker compose exec backend pytest
```

Validar frontend:

```bash
docker compose exec frontend npm run lint
docker compose exec frontend npm run build
```

Parar servicos:

```bash
docker compose stop
```

## Como Rodar Backend Local com Venv

Entre no backend:

```bash
cd backend
```

Crie ambiente virtual:

```bash
python -m venv .venv
```

Instale dependencias:

```bash
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Rode migrations usando variaveis de ambiente configuradas:

```bash
.\.venv\Scripts\alembic.exe upgrade head
```

Rode a API:

```bash
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Rode testes:

```bash
.\.venv\Scripts\python.exe -m pytest
```

Rode lint:

```bash
.\.venv\Scripts\python.exe -m ruff check app tests alembic --no-cache
```

## Scripts Disponiveis

Backend usa `pyproject.toml` e comandos Python:

```bash
python -m pytest
python -m ruff check app tests alembic --no-cache
alembic upgrade head
alembic upgrade head --sql
uvicorn app.main:app --reload
```

Frontend usa scripts do `frontend/package.json`:

```bash
npm run dev      # next dev -H 0.0.0.0
npm run build    # next build
npm run start    # next start
npm run lint     # eslint .
```

## Variaveis de Ambiente

Arquivo base: `.env.example`.

```bash
APP_ENV=local
APP_NAME=Notas de Devolucao SaaS
API_V1_PREFIX=/api/v1

DATABASE_URL=postgresql+asyncpg://app:app@postgres:5432/notas_devolucao
REDIS_URL=redis://redis:6379/0

JWT_SECRET_KEY=change-me-local-placeholder
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
ENCRYPTION_KEY=MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=

CORS_ORIGINS=http://localhost:3000

TINY_API_BASE_URL=https://api.tiny.com.br
MERCADO_LIVRE_CLIENT_ID=placeholder
MERCADO_LIVRE_CLIENT_SECRET=placeholder
SHOPEE_CLIENT_ID=placeholder
SHOPEE_CLIENT_SECRET=placeholder

STORAGE_ENDPOINT_URL=http://localhost:9000
STORAGE_BUCKET_NAME=notas-devolucao-local
STORAGE_ACCESS_KEY=placeholder
STORAGE_SECRET_KEY=placeholder

NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Notas:

- `JWT_SECRET_KEY` deve ser forte fora de ambiente local.
- `ENCRYPTION_KEY` deve decodificar para 32 bytes em base64/url-safe base64.
- `DATABASE_URL` dentro do Docker aponta para `postgres`; localmente pode apontar para `localhost`.
- O provider local atual salva objetos em `.local-storage` relativo ao processo do backend; no Compose isso corresponde a `backend/.local-storage/`, ignorado pelo git.
- As variaveis `STORAGE_*` permanecem no contrato de ambiente para futura troca por storage externo.
- Segredos reais nao devem ir para commits.

## Testes

Suite atual:

```bash
.\.venv\Scripts\python.exe -m pytest
```

Cobertura existente:

- `test_health.py`: health check da API.
- `test_audit_logs.py`: historico operacional, eventos de emissao, filtros, paginacao, isolamento multi-tenant e bloqueio de metadata sensivel.
- `test_domain_models.py`: tabelas, constraints, indices e metadata SQLAlchemy.
- `test_auth.py`: registro, login, tokens, refresh, usuario inativo e rota protegida.
- `test_encryption.py`: AES-GCM, payload invalido, chave invalida e schema publico.
- `test_companies.py`: empresas, vinculos, acesso cross-tenant e vinculo inativo.
- `test_company_role_authorization.py`: matriz de permissoes por role para usuarios, integracoes, emissao, documentos e retencao.
- `test_integrations.py`: integracoes, credenciais criptografadas, settings seguros e isolamento multi-tenant.
- `test_emission_batches_mock.py`: criacao de lotes, jobs, status de notas, isolamento multi-tenant e processamento mockado.
- `test_fiscal_documents_storage.py`: criacao, listagem, download, checksum e isolamento de documentos fiscais.
- `test_local_storage.py`: provider local, validacao de bucket/object key, path traversal e leitura/escrita.
- `test_mock_integrations.py`: clients mockados de Tiny, Mercado Livre e Shopee, erros controlados e ausencia de segredos.
- `test_retention.py`: transicoes para `COLD`/`DELETED`, uso de `retention_until`, idempotencia e auditoria.
- `test_return_orders_mock_sync.py`: sincronizacao mockada de devolucoes, idempotencia e isolamento multi-tenant.
- `test_return_notes_mock_creation.py`: criacao mockada de nota de entrada, vinculo com NF-e original simulada, duplicidade e erros do Tiny mock.
- `test_scheduler.py`: ciclo de retencao recorrente e configuracao do APScheduler.

Os testes de API usam PostgreSQL local real quando disponivel. Se o banco nao estiver acessivel, testes dependentes de banco podem ser pulados por fixture.

Validacao recomendada antes de qualquer entrega:

```bash
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests alembic --no-cache
.\.venv\Scripts\alembic.exe upgrade head --sql
```

## Observabilidade e Jobs

Estado atual:

- `GET /health` valida disponibilidade basica da API.
- Redis esta preparado no Compose.
- Celery worker executa `health.ping` e `emissions.process_mock_batch`.
- APScheduler executa ciclo recorrente de retencao a cada 5 minutos em `America/Sao_Paulo`.
- `retention_jobs` registra execucao, conclusao e falha do ciclo de retencao por empresa.

Ainda nao existem metricas historicas, tracing distribuido ou logs estruturados consolidados.

## Decisoes de Arquitetura Consolidadas

- O backend e a fonte de verdade para autenticacao e autorizacao.
- Frontend nao deve decidir acesso a recurso; no maximo melhora UX.
- `company_id` e fronteira obrigatoria de tenant em dados operacionais.
- Rotas de empresas e integracoes retornam `404` para recursos inacessiveis, reduzindo exposicao de existencia entre tenants.
- Rotas com recurso fiscal tambem devem responder sem vazar existencia cross-tenant.
- `settings` e somente para dados nao sensiveis.
- Credenciais externas pertencem a `encrypted_credentials`.
- Documentos fiscais pertencem ao storage boundary; rotas e services nunca devem manipular paths diretamente.
- `retention_until` e a base da politica de retencao, nao `created_at`.
- Integracoes reais so devem ser adicionadas depois de clients isolados, tratamento de erro, timeout, idempotencia e testes adequados.
- Regra fiscal nao deve ficar dentro de rotas.
- Nenhum fluxo deve implementar estoque.

## Status Atual

Status: MVP tecnico mockado funcional em desenvolvimento local.

Ja implementado:

- Auth JWT;
- bcrypt para senha;
- AES-GCM para credenciais;
- autorizacao por role de empresa;
- models SQLAlchemy principais;
- migrations Alembic iniciais;
- rotas de empresas e usuarios vinculados;
- rotas de integracoes sem chamada externa;
- mocks isolados de Tiny, Mercado Livre e Shopee;
- sincronizacao mockada de devolucoes;
- cruzamento mockado com NF original;
- criacao mockada de nota de entrada em `DRAFT`;
- lotes e jobs de emissao mockada;
- processamento mockado de emissao via service e wrapper Celery;
- storage local de XML/DANFE mockados com checksum SHA-256;
- rotas de listagem e download de documentos fiscais;
- tela frontend de documentos fiscais;
- retencao por `retention_until` com transicoes `COLD` e `DELETED`;
- rota manual de retencao para `OWNER`/`ADMIN`;
- scheduler periodico de retencao com `retention_jobs`;
- historico operacional de eventos de emissao em `audit_logs`;
- auditoria de transicoes de retencao;
- frontend autenticado minimo;
- testes reais de API e banco;

Ainda nao implementado:

- conexao real com Tiny;
- conexao real com Mercado Livre;
- conexao real com Shopee;
- emissao real em lote;
- armazenamento externo de XML/DANFE em S3/R2/B2/Wasabi;
- cold storage real;
- frontend completo de producao.

## Roadmap

Proximos passos sugeridos:

1. Criar auditoria para mudancas sensiveis fora dos fluxos de emissao e retencao.
2. Melhorar frontend com listagens persistidas de notas/devolucoes quando o backend expuser endpoints dedicados.
3. Extrair interface formal de storage para permitir S3/R2/B2/Wasabi sem acoplar services ao provider local.
4. Implementar cold storage externo real e politica operacional de exclusao fisica.
5. Criar fluxo real de busca de devolucoes com idempotencia.
6. Criar fluxo real de cruzamento com NF-e original.
7. Adicionar integracoes reais com Tiny, Mercado Livre e Shopee apos mocks e testes.
8. Evoluir emissao real em lote somente apos validacao fiscal e contratos reais do Tiny.
9. Migrar sessao frontend para estrategia mais segura antes de producao.

ATENCAO: qualquer decisao fiscal precisa ser validada com contador ou especialista fiscal antes de uso em producao.
