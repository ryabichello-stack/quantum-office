const API_URL = process.env.NEXT_PUBLIC_DELNO_API_URL || "http://127.0.0.1:18020";
export const ADMIN_TOKEN_KEY = "delno_admin_token";

export type AdminUser = {
  id: string;
  email: string;
  role: string;
  tenant_slug: string;
};

export type SecretItem = {
  key: string;
  label: string;
  hint?: string;
  sensitive: boolean;
  configured: boolean;
  preview?: string;
  value?: string;
  control?: "text" | "password" | "select";
  options_key?: "chat_models" | "realtime_models" | "realtime_voices" | null;
};

export type SecretGroup = {
  id: string;
  title: string;
  items: SecretItem[];
};

export type OpenAiOptions = {
  source: string;
  fetched_at: number;
  fetch_error?: string | null;
  chat_models: string[];
  realtime_models: string[];
  realtime_voices: string[];
};

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
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

export async function apiMe(token: string) {
  const res = await fetch(`${API_URL}/v1/auth/me`, { headers: authHeaders(token) });
  if (!res.ok) throw new Error("Auth failed");
  return res.json() as Promise<AdminUser>;
}

export async function apiGetTenants(token: string) {
  const res = await fetch(`${API_URL}/v1/admin/tenants`, { headers: authHeaders(token) });
  if (!res.ok) throw new Error("Failed to load tenants");
  return res.json();
}

export async function apiGetCmsPages(token: string) {
  const res = await fetch(`${API_URL}/v1/admin/cms/pages`, { headers: authHeaders(token) });
  if (!res.ok) throw new Error("Failed to load CMS pages");
  return res.json();
}

export async function apiGetPlatformSecrets(token: string) {
  const res = await fetch(`${API_URL}/v1/admin/platform-secrets`, { headers: authHeaders(token) });
  if (!res.ok) throw new Error("Failed to load secrets");
  return res.json() as Promise<{
    env_file: { path: string; exists: boolean; writable: boolean };
    groups: SecretGroup[];
    options: OpenAiOptions;
  }>;
}

export async function apiRefreshPlatformOptions(token: string) {
  const res = await fetch(`${API_URL}/v1/admin/platform-secrets/options/refresh`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error("Failed to refresh options");
  return res.json() as Promise<OpenAiOptions>;
}

export type OpenAiKeyTestResult = {
  ok: boolean;
  error?: string;
  key_preview?: string;
  key_length?: number;
  models_total?: number;
  chat_models_count?: number;
  realtime_models_count?: number;
};

export async function apiTestOpenAiKey(token: string, apiKey?: string) {
  const res = await fetch(`${API_URL}/v1/admin/platform-secrets/openai/test`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ api_key: apiKey ? apiKey.replace(/\s+/g, "") : null }),
  });
  const text = await res.text();
  if (!res.ok) {
    let detail = text.slice(0, 200);
    try {
      detail = JSON.parse(text).detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail || "Key test failed");
  }
  return JSON.parse(text) as OpenAiKeyTestResult;
}

export async function apiPatchPlatformSecrets(token: string, values: Record<string, string>) {
  const res = await fetch(`${API_URL}/v1/admin/platform-secrets`, {
    method: "PATCH",
    headers: authHeaders(token),
    body: JSON.stringify({ values }),
  });
  const text = await res.text();
  if (!res.ok) {
    let detail = text.slice(0, 200);
    try {
      detail = JSON.parse(text).detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail || "Save failed");
  }
  return JSON.parse(text) as { ok: boolean; changed: string[] };
}

export { API_URL };
