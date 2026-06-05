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
- rotas multi-tenant para empresas, usuarios vinculados e integracoes;
- sanitizacao de erros de validacao para nao vazar payload sensivel;
- testes reais contra API e PostgreSQL local;
- Docker Compose para ambiente local completo.

Nao existe, nesta etapa:

- controle de estoque;
- balanceamento de estoque;
- integracao real com Tiny, Mercado Livre ou Shopee;
- emissao real de NF-e;
- regra fiscal definitiva;
- frontend autenticado completo;
- mocks de marketplaces ou ERP.

## Principais Funcionalidades

- **Autenticacao JWT**: registro, login, refresh token e endpoint `me`.
- **Senhas seguras**: senhas sao persistidas apenas como hash bcrypt.
- **Multi-tenant por empresa**: empresas sao acessadas somente por usuarios vinculados em `company_users`.
- **Criacao de empresa com OWNER automatico**: ao criar uma empresa, o usuario autenticado vira `OWNER`.
- **Vinculo de usuarios a empresas**: usuarios existentes podem ser vinculados com roles `OWNER`, `ADMIN`, `OPERATOR` ou `VIEWER`.
- **Integracoes por empresa**: cadastro, listagem, consulta e atualizacao de integracoes por `company_id`.
- **Credenciais criptografadas**: `access_token`, `refresh_token`, `api_token` e `client_secret` sao armazenados em `encrypted_credentials`.
- **Settings nao sensiveis**: `settings` rejeita campos sensiveis para evitar token em texto puro.
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
10. API publica nunca retorna `password_hash`, tokens ou `encrypted_credentials`.

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
- Erros 422 sao sanitizados para remover `input`, `ctx` e `url`.
- Credenciais nao aparecem em responses publicas.

Variaveis sensiveis nunca devem ser commitadas com valores reais.

## Interface

O frontend fica em `frontend/` e usa Next.js.

Arquivos principais atuais:

- `frontend/app/page.tsx`: tela operacional inicial;
- `frontend/app/layout.tsx`: layout base;
- `frontend/app/globals.css`: estilos globais;
- `frontend/components/api-health-badge.tsx`: status da API.

O frontend atual e uma tela inicial operacional. Ele ainda nao implementa fluxo completo de login, cadastro de empresa ou integracoes.

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
          auth.py
          companies.py
          health.py
          integrations.py
    core/
      config.py
      encryption.py
      security.py
    db/
      base.py
      session.py
    integrations/
      mercado_livre/
      shopee/
      tiny/
    jobs/
      scheduler.py
    models/
      domain.py
    repositories/
      companies.py
      integrations.py
      users.py
    schemas/
      auth.py
      companies.py
      health.py
      integrations.py
    services/
      auth.py
      companies.py
      integration_credentials.py
      integrations.py
    workers/
      celery_app.py
      tasks.py
  tests/
    test_auth.py
    test_companies.py
    test_domain_models.py
    test_encryption.py
    test_health.py
    test_integrations.py
  pyproject.toml

frontend/
  app/
    globals.css
    layout.tsx
    page.tsx
  components/
    api-health-badge.tsx
  hooks/
  services/
  types/
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
- Segredos reais nao devem ir para commits.

## Testes

Suite atual:

```bash
.\.venv\Scripts\python.exe -m pytest
```

Cobertura existente:

- `test_health.py`: health check da API.
- `test_domain_models.py`: tabelas, constraints, indices e metadata SQLAlchemy.
- `test_auth.py`: registro, login, tokens, refresh, usuario inativo e rota protegida.
- `test_encryption.py`: AES-GCM, payload invalido, chave invalida e schema publico.
- `test_companies.py`: empresas, vinculos, acesso cross-tenant e vinculo inativo.
- `test_integrations.py`: integracoes, credenciais criptografadas, settings seguros e isolamento multi-tenant.

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
- Celery worker esta preparado em `backend/app/workers`.
- APScheduler esta preparado em `backend/app/jobs/scheduler.py`.

Ainda nao existem metricas historicas, tracing distribuido ou logs estruturados consolidados.

## Decisoes de Arquitetura Consolidadas

- O backend e a fonte de verdade para autenticacao e autorizacao.
- Frontend nao deve decidir acesso a recurso; no maximo melhora UX.
- `company_id` e fronteira obrigatoria de tenant em dados operacionais.
- Rotas de empresas e integracoes retornam `404` para recursos inacessiveis, reduzindo exposicao de existencia entre tenants.
- `settings` e somente para dados nao sensiveis.
- Credenciais externas pertencem a `encrypted_credentials`.
- Integracoes reais so devem ser adicionadas depois de clients isolados, tratamento de erro, timeout, idempotencia e testes adequados.
- Regra fiscal nao deve ficar dentro de rotas.
- Nenhum fluxo deve implementar estoque.

## Status Atual

Status: base backend funcional em desenvolvimento local.

Ja implementado:

- Auth JWT;
- bcrypt para senha;
- AES-GCM para credenciais;
- models SQLAlchemy principais;
- migrations Alembic iniciais;
- rotas de empresas e usuarios vinculados;
- rotas de integracoes sem chamada externa;
- testes reais de API e banco;
- frontend operacional inicial.

Ainda nao implementado:

- conexao real com Tiny;
- conexao real com Mercado Livre;
- conexao real com Shopee;
- busca de devolucoes;
- cruzamento com NF original;
- criacao de nota de entrada;
- emissao em lote;
- armazenamento real de XML/DANFE em S3/R2/B2/Wasabi;
- cold storage real;
- frontend autenticado completo.

## Roadmap

Proximos passos sugeridos sem mocks obrigatorios:

1. Fortalecer testes de contrato com cenarios de banco e tenant boundary.
2. Criar clients isolados para Tiny, Mercado Livre e Shopee sem ainda acoplar regras fiscais.
3. Implementar storage abstraction para documentos fiscais.
4. Criar auditoria para mudancas sensiveis em integracoes.
5. Criar rotas de marketplace accounts.
6. Criar fluxo real de busca de devolucoes com idempotencia.
7. Criar fluxo de cruzamento com NF-e original.
8. Preparar emissao em lote via Celery.
9. Implementar historico e erros operacionais.
10. Implementar cold storage e politica de retencao.

ATENCAO: qualquer decisao fiscal precisa ser validada com contador ou especialista fiscal antes de uso em producao.
