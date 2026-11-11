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
  checks: Record<string, { ok: boolean; detail?: string; optional?: boolean }>;
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
