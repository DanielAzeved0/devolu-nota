export type HealthResponse = {
  status: "ok";
  service: "api";
};

export type AuthTokens = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
};

export type UserPublic = {
  id: string;
  email: string;
  name: string;
  status: string;
  created_at: string;
};

export type CompanyPublic = {
  id: string;
  legal_name: string;
  trade_name: string | null;
  document: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type IntegrationPublic = {
  id: string;
  company_id: string;
  provider: "TINY" | "MERCADO_LIVRE" | "SHOPEE";
  status: string;
  settings: Record<string, unknown> | null;
  last_sync_at: string | null;
  created_at: string;
  updated_at: string;
};

export type MarketplaceProvider = "MERCADO_LIVRE" | "SHOPEE";
export type MockIntegrationScenario = "success" | "invalid_token" | "timeout" | "external_error";
export type MockEmissionScenario = "success" | "partial_failure" | "failure";

export type ReturnOrderPublic = {
  id: string;
  company_id: string;
  marketplace: MarketplaceProvider;
  external_order_id: string;
  status: string;
  original_nfe_key: string | null;
  customer_document: string | null;
  customer_name: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type ReturnOrderMockSyncResponse = {
  company_id: string;
  marketplace: MarketplaceProvider;
  created: number;
  updated: number;
  skipped: number;
  items: ReturnOrderPublic[];
};

export type ReturnNotePublic = {
  id: string;
  company_id: string;
  return_order_id: string;
  status: string;
  original_nfe_key: string | null;
  return_nfe_key: string | null;
  number: string | null;
  series: string | null;
  issued_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type EmissionJobPublic = {
  id: string;
  company_id: string;
  batch_id: string;
  return_note_id: string;
  status: string;
  attempts: number;
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

export type EmissionBatchPublic = {
  id: string;
  company_id: string;
  requested_by_user_id: string | null;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export type EmissionBatchCreatedResponse = EmissionBatchPublic & {
  jobs: EmissionJobPublic[];
};

export type AuditLogPublic = {
  id: string;
  company_id: string;
  user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

export type AuditLogListResponse = {
  items: AuditLogPublic[];
  limit: number;
  offset: number;
};

export type FiscalDocumentPublic = {
  id: string;
  company_id: string;
  return_note_id: string;
  document_type: "NFE_XML" | "DANFE_PDF" | "TINY_JSON" | "SEFAZ_EVENT";
  status: string;
  access_key: string | null;
  xml_storage_archive_id: string | null;
  pdf_storage_archive_id: string | null;
  issued_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
};

export type FiscalDocumentListResponse = {
  items: FiscalDocumentPublic[];
  limit: number;
  offset: number;
};

export type ApiError = {
  message: string;
  status?: number;
};
