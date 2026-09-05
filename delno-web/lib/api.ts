export const API_URL = process.env.NEXT_PUBLIC_DELNO_API_URL || "http://127.0.0.1:18020";

export type TenantMe = {
  tenant_id: string;
  tenant_slug: string;
  tenant_name?: string;
  public_key?: string;
  user_id: string | null;
  role: string | null;
};

export type LeadItem = {
  id: string;
  name: string;
  phone: string;
  email: string | null;
  company: string | null;
  website: string | null;
  inn: string | null;
  source: string;
  status: string;
  party_enriched: boolean;
  created_at: string | null;
};

export type ConversationItem = {
  id: string;
  channel: string;
  channel_label?: string;
  status: string;
  contact_ref?: string | null;
  visitor_name?: string | null;
  visitor_phone?: string | null;
  visitor_phone_masked?: string | null;
  lead_id?: string | null;
  last_message_preview?: string | null;
  message_count?: number | null;
  is_new?: boolean;
  created_at: string | null;
  updated_at?: string | null;
};

export type ConversationDetail = ConversationItem & {
  subtitle?: string;
  summary?: string | null;
  tags?: string[];
  recording_url?: string | null;
  recording_duration_sec?: number | null;
  call_status?: string | null;
};

export type MessageItem = {
  id: string;
  role: string;
  body: string;
  meta: Record<string, unknown> | null;
  created_at: string | null;
};

export type KnowledgeSource = {
  document_id?: string;
  chunk_id?: string;
  title?: string;
  citation?: string;
  snippet_preview?: string;
};

export type PendingConfirmation = {
  confirmation_id: string;
  tool_name: string;
  params: Record<string, unknown>;
  summary: string;
};

export type OnboardingStatus = {
  ok?: boolean;
  status: string;
  conversation_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  draft?: Record<string, unknown>;
};

export type OnboardingUploadItem = {
  upload_id: string;
  file_name: string;
  size_bytes: number;
  parse_status: string;
  document_id?: string | null;
  created_at?: string | null;
  meta?: Record<string, unknown>;
};

export type OnboardingUploadResult = {
  ok: boolean;
  upload_id?: string;
  file_name?: string;
  size_bytes?: number;
  parse_status?: string;
  document_id?: string | null;
  extract_method?: string;
  reply?: string;
  error?: string;
  conversation_id?: string | null;
};

export type OnboardingSummaryProfile = {
  company_name?: string | null;
  services?: string[];
  prices?: string[];
  address?: string | null;
  hours?: string | null;
  contacts?: string | null;
  conditions?: string | null;
  faq?: string[];
};

export type OnboardingConflict = {
  field: string;
  label: string;
  values: Array<{ price: number; source_type: string; source_label: string }>;
};

export type OnboardingSummary = {
  ok: boolean;
  status: string;
  summary_ready: boolean;
  profile: OnboardingSummaryProfile;
  missing_fields: string[];
  conflicts: OnboardingConflict[];
  document_ids: string[];
  sources_count: number;
  summary_text?: string;
};

export type OnboardingStartResult = {
  ok: boolean;
  resumed: boolean;
  conversation_id: string;
  status: string;
  reply: string;
};

export type FeatureFlag = {
  flag_key: string;
  enabled: boolean;
};

export type PartySuggestion = {
  value?: string | null;
  inn?: string | null;
  company_name?: string | null;
  address?: string | null;
};

export type LegalProfile = {
  inn?: string;
  company_name?: string;
  address?: string;
  okved?: string;
  ogrn?: string;
  ogrnip?: string;
  enriched_at?: string;
};

async function apiFetch<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.headers || {}),
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function apiLogin(email: string, password: string) {
  const res = await fetch(`${API_URL}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error("Login failed");
  return res.json() as Promise<{ access_token: string }>;
}

export async function apiRegister(body: {
  email: string;
  password: string;
  company_name: string;
  inn?: string;
  slug?: string;
}) {
  const res = await fetch(`${API_URL}/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Register failed");
  return res.json() as Promise<{
    access_token: string;
    tenant_slug: string;
    tenant_name: string;
    public_key: string;
  }>;
}

export function apiTenantWidget(token: string) {
  return apiFetch<{
    site_key: string;
    embed_html: string;
    cdn_base: string;
    api_base: string;
  }>("/v1/tenant/widget", token);
}

export function apiKnowledgeUpload(token: string, title: string, body: string) {
  return apiFetch<{ ok: boolean; document_id?: string }>("/v1/tenant/knowledge/documents", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, body, visibility: "public" }),
  });
}

export type KnowledgeDocumentItem = {
  document_id: string | null;
  title: string | null;
  source: string | null;
  published_at: string | null;
};

export function apiKnowledgeList(token: string, limit = 50) {
  return apiFetch<{ items: KnowledgeDocumentItem[]; total: number }>(
    `/v1/tenant/knowledge/documents?limit=${limit}`,
    token,
  );
}

export type InstantDemoResult = {
  ok: boolean;
  job_id: string;
  url: string;
  title: string;
  document_id?: string;
  site_key: string;
  widget_embed: string;
  sample_questions: string[];
};

export function apiInstantDemoImport(token: string, websiteUrl: string) {
  return apiFetch<InstantDemoResult>("/v1/tenant/instant-demo", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ website_url: websiteUrl }),
  });
}

export function apiTenantMe(token: string) {
  return apiFetch<TenantMe>("/v1/tenant/me", token);
}

export function apiLeadsList(token: string, limit = 50) {
  return apiFetch<{ items: LeadItem[] }>(`/v1/leads?limit=${limit}`, token);
}

export function apiConversations(token: string, limit = 50, q?: string, filter?: string) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (q?.trim()) params.set("q", q.trim());
  if (filter) params.set("filter", filter);
  return apiFetch<{ items: ConversationItem[]; total: number; new_count: number }>(
    `/v1/operator/conversations?${params}`,
    token,
  );
}

export function apiConversationDetail(token: string, conversationId: string) {
  return apiFetch<ConversationDetail>(`/v1/operator/conversations/${conversationId}`, token);
}

export function apiConversationMessages(token: string, conversationId: string) {
  return apiFetch<{ items: MessageItem[] }>(`/v1/operator/conversations/${conversationId}/messages`, token);
}

export function apiOperatorChat(
  token: string,
  message: string,
  conversationId?: string,
  modality: "text" | "voice" = "text",
  channel = "cabinet",
) {
  return apiFetch<{
    conversation_id: string;
    reply: string;
    sources: KnowledgeSource[];
    tool_calls: unknown[];
    pending_confirmation: PendingConfirmation | null;
  }>("/v1/operator/chat", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      channel,
      conversation_id: conversationId || null,
      modality,
    }),
  });
}

export function apiOnboardingStart(token: string, forceNew = false) {
  return apiFetch<OnboardingStartResult>("/v1/tenant/onboarding/start", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force_new: forceNew }),
  });
}

export function apiOnboardingStatus(token: string) {
  return apiFetch<OnboardingStatus>("/v1/tenant/onboarding/status", token);
}

export function apiOnboardingUploads(token: string, conversationId?: string) {
  const params = new URLSearchParams();
  if (conversationId) params.set("conversation_id", conversationId);
  const qs = params.toString();
  return apiFetch<{ items: OnboardingUploadItem[]; total: number }>(
    `/v1/tenant/onboarding/uploads${qs ? `?${qs}` : ""}`,
    token,
  );
}

export async function apiOnboardingUpload(token: string, file: File, conversationId?: string) {
  const form = new FormData();
  form.append("file", file);
  if (conversationId) form.append("conversation_id", conversationId);
  const res = await fetch(`${API_URL}/v1/tenant/onboarding/upload`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: form,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<OnboardingUploadResult>;
}

export function apiOnboardingSummary(token: string) {
  return apiFetch<OnboardingSummary>("/v1/tenant/onboarding/summary", token);
}

export function apiOnboardingPublish(token: string) {
  return apiFetch<{ ok: boolean; message?: string; error?: string; published?: unknown[] }>(
    "/v1/tenant/onboarding/publish",
    token,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: true }),
    },
  );
}

export function apiOnboardingResolveConflict(token: string, field: string, canonicalValue: string | number) {
  return apiFetch<{ ok: boolean }>("/v1/tenant/onboarding/conflicts/resolve", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, canonical_value: canonicalValue }),
  });
}

export function apiOperatorConfirm(token: string, toolName: string, params: Record<string, unknown>) {
  return apiFetch<{ ok: boolean; message: string; data: Record<string, unknown> }>(
    "/v1/operator/confirm",
    token,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_name: toolName, params }),
    },
  );
}

export function apiTenantLegalGet(token: string) {
  return apiFetch<{ ok: boolean; legal: LegalProfile | null }>("/v1/tenant/legal", token);
}

export function apiTenantLegalPut(token: string, inn: string) {
  return apiFetch<{ ok: boolean; legal: LegalProfile; party_enriched: boolean }>("/v1/tenant/legal", token, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inn }),
  });
}

export function apiPartySuggest(token: string, q: string, count = 6) {
  return apiFetch<{ ok: boolean; suggestions: PartySuggestion[] }>(
    `/v1/tenant/party/suggest?q=${encodeURIComponent(q)}&count=${count}`,
    token,
  );
}

export function apiFeatureFlags(token: string) {
  return apiFetch<FeatureFlag[]>("/v1/tenant/feature-flags", token);
}

export function apiPatchFeatureFlag(token: string, flagKey: string, enabled: boolean) {
  return apiFetch<FeatureFlag>(`/v1/tenant/feature-flags/${flagKey}`, token, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}
