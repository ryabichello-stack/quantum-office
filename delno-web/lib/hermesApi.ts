import { apiFetch } from "./api";

export type HermesSetupStep = {
  id: string;
  title: string;
  hint: string;
};

export type HermesSetupStatus = {
  ok: boolean;
  tenant_slug: string;
  setup_complete: boolean;
  progress: { required_done: number; required_total: number };
  checks: Record<string, { ok: boolean; detail?: unknown; optional?: boolean }>;
  steps: HermesSetupStep[];
  next_steps: Array<HermesSetupStep & { status?: string }>;
  hermes?: {
    setup_started_at?: string;
    setup_completed_at?: string;
    last_health_at?: string;
    open_alerts?: unknown[];
  };
  message_ru: string;
};

export type HermesAlert = {
  code: string;
  severity: string;
  message_ru: string;
  fix?: string;
};

export type HermesHealthStatus = {
  ok: boolean;
  healthy: boolean;
  alerts: HermesAlert[];
  telephony?: {
    active_dids: number;
    queued_jobs: number;
    stuck_jobs: number;
    recent_failed_sessions: number;
  };
  channels?: Array<{ type: string; status: string; id: string }>;
  connectors?: Array<Record<string, unknown>>;
  message_ru: string;
  checked_at?: string;
};

export type PhoneNumberItem = {
  id: string;
  e164: string;
  label?: string | null;
  status: string;
  provider?: string;
  purpose?: string;
  inbound_enabled?: boolean;
  outbound_enabled?: boolean;
};

export type CallSessionItem = {
  id: string;
  direction: string;
  state: string;
  from_e164?: string | null;
  to_e164?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  disposition?: string | null;
};

export function apiHermesSetup(token: string) {
  return apiFetch<HermesSetupStatus>("/v1/telephony/hermes/setup", token);
}

export function apiHermesHealth(token: string) {
  return apiFetch<HermesHealthStatus>("/v1/telephony/hermes/health", token);
}

export function apiPhonesList(token: string) {
  return apiFetch<{ ok?: boolean; items: PhoneNumberItem[] }>("/v1/tenant/phones", token);
}

export function apiPhonesProvision(
  token: string,
  body: { e164: string; label?: string; status?: string },
) {
  return apiFetch<{ ok: boolean; phone?: PhoneNumberItem; created?: boolean }>("/v1/tenant/phones", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function apiCallsList(token: string, limit = 20) {
  return apiFetch<{ ok: boolean; items: CallSessionItem[] }>(`/v1/telephony/sessions?limit=${limit}`, token);
}

export function apiCallDial(token: string, body: { to_e164: string; script?: string }) {
  return apiFetch<{ ok: boolean; session?: CallSessionItem; job?: Record<string, unknown> }>(
    "/v1/telephony/dial",
    token,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export type LlmCostTotals = {
  events: number;
  prompt_tokens: number;
  completion_tokens: number;
  tokens_total: number;
  cost_client_rub: number;
  cost_vendor_usd: number;
  margin_rub_approx?: number;
};

export type BillingSummary = {
  ok: boolean;
  balance: { currency: string; token_credits: number; granted_credits: number; spent_credits: number };
  tariff: Record<string, number | string>;
  llm?: LlmCostTotals;
  by_metric: Array<{ metric: string; quantity: number; events: number }>;
  message_ru: string;
};

export type PlatformBillingOverview = {
  ok: boolean;
  currency_client: string;
  currency_vendor: string;
  totals: LlmCostTotals;
  tenants: Array<{
    tenant_id: string;
    tenant_slug: string;
    tenant_name: string;
    llm: LlmCostTotals;
    balance: BillingSummary["balance"];
  }>;
  message_ru: string;
};

export function apiBillingSummary(token: string) {
  return apiFetch<BillingSummary>("/v1/tenant/billing/summary", token);
}

export function apiBillingEnsure(token: string) {
  return apiFetch<BillingSummary>("/v1/tenant/billing/ensure", token, { method: "POST" });
}

export function apiAdminBillingOverview(token: string) {
  return apiFetch<PlatformBillingOverview>("/v1/admin/billing/overview", token);
}

export function apiChannelQrStart(token: string, channel_type: string, label?: string) {
  return apiFetch<{
    ok: boolean;
    account_id: string;
    login_id: string;
    status: string;
    message_ru: string;
    auth_mode: string;
  }>("/v1/tenant/channels/qr/start", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channel_type, label }),
  });
}

/** Nous Hermes product loop (P1+) — available even when runtime flag is off. */
export type OfficeLoopStep = {
  id: string;
  title: string;
  done: boolean;
  hint: string;
};

export type OfficeLoopStatus = {
  ok: boolean;
  phase: string;
  steps: OfficeLoopStep[];
  next_step?: OfficeLoopStep;
  kb_ok?: boolean;
  kb_draft?: { title?: string; body?: string; status?: string; source_url?: string } | null;
  connectors_ready_count?: number;
  ui?: { headline?: string; primary_cta?: { title: string; text: string } };
  setup?: { setup_complete?: boolean; message_ru?: string };
};

export type HermesNousStatus = {
  ok: boolean;
  enabled: boolean;
  engine?: string;
  pin?: string;
  office_loop?: OfficeLoopStatus | null;
  runtime?: Record<string, unknown> | null;
};

export type AgentTaskItem = {
  id: string;
  goal: string;
  trigger_kind: string;
  status: string;
  hermes_cron_id?: string | null;
  created_at?: string | null;
};

export function apiHermesNousStatus(token: string) {
  return apiFetch<HermesNousStatus>("/v1/hermes-nous/status", token);
}

export function apiOfficeLoop(token: string) {
  return apiFetch<OfficeLoopStatus>("/v1/hermes-nous/office-loop", token);
}

export function apiKbDraftConfirm(token: string) {
  return apiFetch<{ ok: boolean; committed?: boolean }>("/v1/hermes-nous/kb-draft/confirm", token, {
    method: "POST",
  });
}

export function apiAgentTasks(token: string, limit = 20) {
  return apiFetch<{ ok: boolean; items: AgentTaskItem[] }>(`/v1/hermes-nous/tasks?limit=${limit}`, token);
}

export function apiAgentTaskCreate(token: string, goal: string, trigger_kind = "manual") {
  return apiFetch<{ ok: boolean; task: AgentTaskItem }>("/v1/hermes-nous/tasks", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal, trigger_kind }),
  });
}
