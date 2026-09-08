const API_URL = process.env.NEXT_PUBLIC_DELNO_API_URL || "http://127.0.0.1:18020";
export const ADMIN_TOKEN_KEY = "delno_admin_token";
const API_TIMEOUT_MS = 45_000;

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

export function clearAdminSession(reason?: string) {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ADMIN_TOKEN_KEY);
  const query = reason ? `?reason=${encodeURIComponent(reason)}` : "";
  window.location.href = `/login${query}`;
}

function parseErrorDetail(text: string): string {
  try {
    const parsed = JSON.parse(text) as { detail?: string | unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) return parsed.detail.map(String).join("; ");
  } catch {
    /* ignore */
  }
  return text.slice(0, 200);
}

async function apiFetch(token: string, path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers,
      signal: AbortSignal.timeout(API_TIMEOUT_MS),
    });
  } catch (err) {
    if (err instanceof Error && err.name === "TimeoutError") {
      throw new Error("request_timeout");
    }
    throw err;
  }

  if (response.status === 401) {
    clearAdminSession("session_expired");
    throw new Error("session_expired");
  }

  return response;
}

export async function apiLogin(email: string, password: string) {
  const res = await fetch(`${API_URL}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
    signal: AbortSignal.timeout(API_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error("Login failed");
  return res.json() as Promise<{ access_token: string }>;
}

export async function apiMe(token: string) {
  const res = await apiFetch(token, "/v1/auth/me");
  if (!res.ok) throw new Error("Auth failed");
  return res.json() as Promise<AdminUser>;
}

export async function apiGetTenants(token: string) {
  const res = await apiFetch(token, "/v1/admin/tenants");
  if (!res.ok) throw new Error("Failed to load tenants");
  return res.json();
}

export async function apiGetCmsPages(token: string) {
  const res = await apiFetch(token, "/v1/admin/cms/pages");
  if (!res.ok) throw new Error("Failed to load CMS pages");
  return res.json();
}

export async function apiGetPlatformSecrets(token: string) {
  const res = await apiFetch(token, "/v1/admin/platform-secrets");
  if (!res.ok) throw new Error(parseErrorDetail(await res.text()) || "Failed to load secrets");
  return res.json() as Promise<{
    env_file: { path: string; exists: boolean; writable: boolean };
    groups: SecretGroup[];
    options: OpenAiOptions;
  }>;
}

export async function apiRefreshPlatformOptions(token: string) {
  const res = await apiFetch(token, "/v1/admin/platform-secrets/options/refresh", { method: "POST" });
  if (!res.ok) throw new Error(parseErrorDetail(await res.text()) || "Failed to refresh options");
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
  const res = await apiFetch(token, "/v1/admin/platform-secrets/openai/test", {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey ? apiKey.replace(/\s+/g, "") : null }),
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(parseErrorDetail(text) || "Key test failed");
  }
  return JSON.parse(text) as OpenAiKeyTestResult;
}

export async function apiPatchPlatformSecrets(token: string, values: Record<string, string>) {
  const res = await apiFetch(token, "/v1/admin/platform-secrets", {
    method: "PATCH",
    body: JSON.stringify({ values }),
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(parseErrorDetail(text) || "Save failed");
  }
  return JSON.parse(text) as { ok: boolean; changed: string[]; relogin_required?: boolean };
}

export { API_URL };
