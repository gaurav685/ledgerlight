// Phase 5 §4: TypeScript types mirroring the real backend's own
// Pydantic response schemas (ledgerlight/api/schemas.py). Kept
// hand-written rather than code-generated -- the real OpenAPI export
// at docs/api/openapi.json is the actual contract; these are checked
// against it by hand whenever a backend schema changes.

export interface IdentityOut {
  user_id: string | null;
  tenant_id: string;
  role: string;
  api_key_id: string | null;
}

export interface LoginResponse {
  identity: IdentityOut;
  csrf_token: string;
}

export interface CompanyOut {
  id: string;
  name: string;
  cin: string | null;
  nse_symbol: string | null;
  bse_code: string | null;
}

export interface EventOut {
  id: string;
  company_id: string;
  event_type_code: string;
  status: string;
  event_time: string | null;
  known_at: string | null;
  summary: string | null;
}

export interface TimelineEntry {
  event_time: string | null;
  known_at: string;
  kind: "event" | "filing";
  label: string;
  tier: string | null;
  event_id: string | null;
  version_id: string | null;
}

export interface ScoreOut {
  company_id: string;
  as_of: string;
  score: number;
  model_version: string;
  shap_contributors: [string, number][] | null;
  model_limitations: string;
}

export interface CredibilityOut {
  company_id: string;
  as_of: string;
  available: boolean;
  reason: string | null;
  value: number | null;
}

export interface InvestigationOut {
  id: string;
  company_id: string;
  as_of: string;
  state: string;
  final_status: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface DossierOut {
  id: string;
  investigation_id: string;
  version: number;
  status: string;
  sections: Record<string, string[]>;
  claim_id_map: Record<string, string[]>;
  created_at: string;
}

export interface ReviewTaskOut {
  id: string;
  dossier_id: string | null;
  claim_id: string | null;
  reason_code: string;
  priority: number;
  status: string;
  assignee: string | null;
  decision: string | null;
  created_at: string;
}

export interface WatchlistOut {
  id: string;
  name: string;
  created_at: string;
}

export interface WatchlistItemOut {
  id: string;
  watchlist_id: string;
  company_id: string;
  added_at: string;
}

export interface AlertRuleOut {
  id: string;
  watchlist_id: string;
  rule_type: string;
  config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
}

export interface AlertOut {
  id: string;
  alert_rule_id: string;
  company_id: string;
  payload: Record<string, unknown>;
  triggered_at: string;
  acknowledged_at: string | null;
}

export interface ApiKeyOut {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyCreateResponse extends Omit<ApiKeyOut, "revoked_at" | "last_used_at"> {
  raw_key: string;
}

export interface WebhookOut {
  id: string;
  url: string;
  is_active: boolean;
  created_at: string;
}

export interface WebhookCreateResponse extends Omit<WebhookOut, never> {
  raw_secret: string;
}

export interface WebhookDeliveryOut {
  id: string;
  webhook_id: string;
  status: string;
  attempt_count: number;
  response_code: number | null;
  created_at: string;
  delivered_at: string | null;
}

export interface UserOut {
  user_id: string;
  email: string;
  role: string;
  membership_status: string;
  is_active: boolean;
  created_at: string;
}

export interface AuditLogOut {
  id: string;
  actor_user_id: string | null;
  actor_api_key_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  created_at: string;
}

export interface SignedDocumentLinkOut {
  url: string;
  expires_in_seconds: number;
}

export interface DocumentPageTextOut {
  page_number: number;
  raw_text: string;
  char_count: number;
}

// Enhancement 1: governance event study (market reaction) -- read-only
// research output, never investment advice, never a trading signal.
export interface EventStudyRunSummaryOut {
  run_id: string;
  spec_version: string;
  spec_sha256: string;
  git_sha: string;
  created_at: string;
  event_counts: Record<string, unknown>;
  metrics: Record<string, unknown>;
  disclaimer: string;
}

export interface EventStudyCompanyEventOut {
  event_type_code: string;
  severity_band: string | null;
  event_date: string;
  is_primary: boolean;
  possible_corporate_action: boolean;
  car_primary_window: number | null;
  type_average_car_primary_window: number | null;
}

export const ROLES = ["viewer", "analyst", "reviewer", "tenant_admin"] as const;
export type Role = (typeof ROLES)[number];
