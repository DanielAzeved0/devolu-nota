import type {
  ApiError,
  AuditLogListResponse,
  AuthTokens,
  CompanyPublic,
  EmissionBatchCreatedResponse,
  FiscalDocumentListResponse,
  HealthResponse,
  IntegrationPublic,
  MarketplaceProvider,
  MockEmissionScenario,
  MockIntegrationScenario,
  ReturnNotePublic,
  ReturnOrderMockSyncResponse,
  UserPublic
} from "@/types/api";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function getApiHealth(): Promise<{ ok: true; data: HealthResponse } | { ok: false }> {
  try {
    const response = await fetch(`${apiBaseUrl}/health`, {
      cache: "no-store"
    });

    if (!response.ok) {
      return { ok: false };
    }

    return { ok: true, data: (await response.json()) as HealthResponse };
  } catch {
    return { ok: false };
  }
}

type ApiOptions = {
  token?: string | null;
  method?: "GET" | "POST" | "PATCH" | "PUT";
  body?: unknown;
  query?: Record<string, string | number | undefined>;
};

export class ApiRequestError extends Error {
  status?: number;

  constructor(error: ApiError) {
    super(error.message);
    this.status = error.status;
  }
}

async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const url = new URL(`${apiBaseUrl}${path}`);
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  const headers: HeadersInit = {
    "Content-Type": "application/json"
  };
  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store"
  });

  if (!response.ok) {
    throw new ApiRequestError({
      status: response.status,
      message: await parseErrorMessage(response)
    });
  }

  return (await response.json()) as T;
}

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (
      payload.detail &&
      typeof payload.detail === "object" &&
      "message" in payload.detail &&
      typeof payload.detail.message === "string"
    ) {
      return payload.detail.message;
    }
  } catch {
    return "Nao foi possivel concluir a operacao.";
  }
  return "Nao foi possivel concluir a operacao.";
}

export function toUiError(error: unknown): ApiError {
  if (error instanceof ApiRequestError) {
    return { message: error.message, status: error.status };
  }
  return { message: "Nao foi possivel conectar com a API." };
}

export function login(payload: { email: string; password: string }) {
  return apiRequest<AuthTokens>("/api/v1/auth/login", { method: "POST", body: payload });
}

export function register(payload: { email: string; name: string; password: string }) {
  return apiRequest<AuthTokens>("/api/v1/auth/register", { method: "POST", body: payload });
}

export function getCurrentUser(token: string) {
  return apiRequest<UserPublic>("/api/v1/auth/me", { token });
}

export function listCompanies(token: string) {
  return apiRequest<CompanyPublic[]>("/api/v1/companies", { token });
}

export function createCompany(
  token: string,
  payload: { legal_name: string; trade_name?: string | null; document: string }
) {
  return apiRequest<CompanyPublic>("/api/v1/companies", { method: "POST", token, body: payload });
}

export function listIntegrations(token: string, companyId: string) {
  return apiRequest<IntegrationPublic[]>(`/api/v1/companies/${companyId}/integrations`, { token });
}

export function createIntegration(
  token: string,
  companyId: string,
  payload: { provider: "TINY" | "MERCADO_LIVRE" | "SHOPEE"; settings?: Record<string, unknown> }
) {
  return apiRequest<IntegrationPublic>(`/api/v1/companies/${companyId}/integrations`, {
    method: "POST",
    token,
    body: { settings: {}, ...payload }
  });
}

export function syncMockReturns(
  token: string,
  companyId: string,
  payload: { marketplace: MarketplaceProvider; scenario: MockIntegrationScenario }
) {
  return apiRequest<ReturnOrderMockSyncResponse>(
    `/api/v1/companies/${companyId}/return-orders/mock-sync`,
    { method: "POST", token, body: payload }
  );
}

export function createMockReturnNote(
  token: string,
  companyId: string,
  returnOrderId: string,
  payload: { scenario: MockIntegrationScenario }
) {
  return apiRequest<ReturnNotePublic>(
    `/api/v1/companies/${companyId}/return-orders/${returnOrderId}/return-notes/mock`,
    { method: "POST", token, body: payload }
  );
}

export function createMockEmissionBatch(
  token: string,
  companyId: string,
  payload: { return_note_ids: string[]; scenario: MockEmissionScenario }
) {
  return apiRequest<EmissionBatchCreatedResponse>(
    `/api/v1/companies/${companyId}/emission-batches/mock`,
    { method: "POST", token, body: payload }
  );
}

export function listAuditLogs(
  token: string,
  companyId: string,
  query: { action?: string; entity_type?: string; limit?: number; offset?: number } = {}
) {
  return apiRequest<AuditLogListResponse>(`/api/v1/companies/${companyId}/audit-logs`, {
    token,
    query
  });
}

export function listFiscalDocuments(
  token: string,
  companyId: string,
  query: { return_note_id?: string; limit?: number; offset?: number } = {}
) {
  return apiRequest<FiscalDocumentListResponse>(
    `/api/v1/companies/${companyId}/fiscal-documents`,
    { token, query }
  );
}

export async function downloadFiscalDocument(
  token: string,
  companyId: string,
  fiscalDocumentId: string
): Promise<Blob> {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/companies/${companyId}/fiscal-documents/${fiscalDocumentId}/download`,
    {
      headers: {
        Authorization: `Bearer ${token}`
      },
      cache: "no-store"
    }
  );

  if (!response.ok) {
    throw new ApiRequestError({
      status: response.status,
      message: await parseErrorMessage(response)
    });
  }

  return response.blob();
}
