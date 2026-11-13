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

export type CallSessionMemory = {
  id: string;
  direction: string;
  status: string;
  from_e164?: string | null;
  to_e164?: string | null;
  did_e164?: string | null;
  outcome?: string | null;
  duration_sec?: number | null;
  summary?: string | null;
  has_transcript?: boolean;
  transcript?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
};

export type ConversationDetail = ConversationItem & {
  subtitle?: string;
  summary?: string | null;
  tags?: string[];
  recording_url?: string | null;
  recording_duration_sec?: number | null;
  call_status?: string | null;
  call_session?: CallSessionMemory | null;
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

export type SuggestedAction = {
  title: string;
  text: string;
};

export type OnboardingStatus = {
  ok?: boolean;
  status: string;
  conversation_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  draft?: Record<string, unknown>;
  ttfv?: {
    started_at?: string | null;
    milestones?: Record<string, string>;
    elapsed_ms?: Record<string, number | null>;
    published?: boolean;
  };
};

export type ChannelAccountItem = {
  id: string;
  type: string;
  status: string;
  bot_username?: string | null;
  bot_name?: string | null;
  webhook_url?: string | null;
  verified_at?: string | null;
  created_at?: string | null;
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

export async function apiFetch<T>(path: string, token: string, init?: RequestInit): Promise<T> {
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

export type KnowledgeTemplateItem = {
  id: string;
  title: string;
  description: string;
  doc_type: string;
  example?: boolean;
  filename: string;
};

export function apiKnowledgeTemplates(token: string, includeExamples = true) {
  return apiFetch<{ items: KnowledgeTemplateItem[]; total: number }>(
    `/v1/tenant/knowledge/templates?include_examples=${includeExamples ? "true" : "false"}`,
    token,
  );
}

export function apiKnowledgeTemplateDownload(token: string, templateId: string) {
  return apiFetch<{
    id: string;
    title: string;
    filename: string;
    body: string;
    content_type: string;
  }>(`/v1/tenant/knowledge/templates/${encodeURIComponent(templateId)}`, token);
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

export function apiConversationDelete(token: string, conversationId: string) {
  return apiFetch<{ ok: boolean; deleted_id: string }>(
    `/v1/operator/conversations/${conversationId}`,
    token,
    { method: "DELETE" },
  );
}

export function apiConversationsBulkDelete(
  token: string,
  body: { ids?: string[]; channel?: string; keep_latest_hermes?: boolean },
) {
  return apiFetch<{ ok: boolean; deleted: number; ids: string[] }>(
    "/v1/operator/conversations/bulk-delete",
    token,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export type OperatorChatAttachment = {
  filename: string;
  content_type: string;
  data_base64: string;
};

export type CredentialFormSpec = {
  kind: string;
  title: string;
  hint?: string;
  fields: Array<{
    name: string;
    label: string;
    type: "text" | "password";
    autocomplete?: string;
  }>;
  submit_label?: string;
  prefill?: Record<string, string>;
  password_required?: boolean;
  login_optional?: boolean;
  require_foreign_consent?: boolean;
  consent_label?: string;
};

export function apiOperatorChat(
  token: string,
  message: string,
  conversationId?: string,
  modality: "text" | "voice" = "text",
  channel = "cabinet",
  attachments?: OperatorChatAttachment[],
) {
  return apiFetch<{
    conversation_id: string;
    reply: string;
    sources: KnowledgeSource[];
    tool_calls: unknown[];
    engine?: string;
    hermes_run?: unknown;
    pending_confirmation: PendingConfirmation | null;
    pending_credential_form?: CredentialFormSpec | null;
    pending_download?: {
      filename: string;
      title: string;
      body: string;
      content_type?: string;
    } | null;
    suggested_actions?: SuggestedAction[];
  }>("/v1/operator/chat", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      channel,
      conversation_id: conversationId || null,
      modality,
      attachments: attachments || [],
    }),
  });
}

export function apiTenantSecretSave(
  token: string,
  body: { kind: string; login?: string; password?: string; foreign_consent?: boolean },
) {
  return apiFetch<{
    ok: boolean;
    kind: string;
    configured: boolean;
    login_masked?: string;
    message?: string;
    pending_credential_form?: CredentialFormSpec | null;
    sip_probe?: {
      ok?: boolean;
      skipped?: boolean;
      applied?: boolean;
      message_ru?: string;
      cursor_task?: string;
      next_actions?: { title: string; text: string }[];
    };
    cloud_probe?: {
      source?: string;
      title?: string;
      message_ru?: string;
      probe?: { ok?: boolean; message_ru?: string; next_actions?: { title: string; text: string }[] };
    };
    channel_connect?: {
      ok?: boolean;
      error?: string;
      account?: { bot_username?: string; status?: string; type?: string };
    };
  }>("/v1/tenant/vault", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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
  return apiFetch<{
    ok: boolean;
    message: string;
    data: Record<string, unknown>;
    suggested_actions?: SuggestedAction[];
    pending_credential_form?: CredentialFormSpec | null;
  }>("/v1/operator/confirm", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool_name: toolName, params }),
  });
}

/** Freeze chat + office state when owner is stuck (onboarding / Hermes bug). */
export function apiOperatorHelp(
  token: string,
  body: {
    conversation_id?: string | null;
    note?: string;
    channel?: string;
    client_meta?: Record<string, unknown>;
  } = {},
) {
  return apiFetch<{
    ok: boolean;
    ticket_id: string;
    event_id: string;
    conversation_id?: string | null;
    message_count?: number;
    message: string;
  }>("/v1/operator/help", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      conversation_id: body.conversation_id || null,
      note: body.note || "",
      channel: body.channel || "hermes",
      client_meta: body.client_meta || {},
    }),
  });
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

export function apiTenantChannels(token: string) {
  return apiFetch<{ items: ChannelAccountItem[]; total: number }>("/v1/tenant/channels", token);
}

export function apiTelegramConnect(token: string, botToken: string) {
  return apiFetch<{ ok: boolean; account: ChannelAccountItem }>("/v1/tenant/channels/telegram/connect", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bot_token: botToken }),
  });
}

export function apiTelegramDisconnect(token: string, accountId: string) {
  return apiFetch<{ ok: boolean; account: ChannelAccountItem }>(
    `/v1/tenant/channels/telegram/${accountId}/disconnect`,
    token,
    { method: "POST" },
  );
}

export function apiTelegramHealth(token: string, accountId: string) {
  return apiFetch<{
    ok: boolean;
    bot?: Record<string, unknown> | null;
    webhook?: { url?: string | null; expected_url?: string; ok?: boolean; pending_update_count?: number | null };
    account?: ChannelAccountItem;
  }>(`/v1/tenant/channels/telegram/${accountId}/health`, token);
}

export function apiMaxConnect(token: string, accessToken: string) {
  return apiFetch<{ ok: boolean; account: ChannelAccountItem }>("/v1/tenant/channels/max/connect", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_token: accessToken }),
  });
}

export function apiMaxDisconnect(token: string, accountId: string) {
  return apiFetch<{ ok: boolean; account: ChannelAccountItem }>(
    `/v1/tenant/channels/max/${accountId}/disconnect`,
    token,
    { method: "POST" },
  );
}

export function apiMaxHealth(token: string, accountId: string) {
  return apiFetch<{
    ok: boolean;
    bot?: Record<string, unknown> | null;
    webhook?: { expected_url?: string; ok?: boolean; subscriptions?: unknown[] };
    account?: ChannelAccountItem;
  }>(`/v1/tenant/channels/max/${accountId}/health`, token);
}
