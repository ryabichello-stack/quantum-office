const API_URL = process.env.NEXT_PUBLIC_DELNO_API_URL || "http://127.0.0.1:18020";

async function adminGet<T>(token: string, path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`Failed: ${path}`);
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

export async function apiGetTenants(token: string) {
  return adminGet<Array<{ id: string; slug: string; name: string }>>(token, "/v1/admin/tenants");
}

export async function apiGetCmsPages(token: string) {
  return adminGet<Array<{ slug: string; title: string; status: string }>>(
    token,
    "/v1/admin/cms/pages",
  );
}

export type AnalyticsSummary = {
  site_key: string;
  days: number;
  since: string;
  sessions: number;
  pageviews: number;
  bounce_rate: number;
  pages_per_session: number;
  engaged_sessions: number;
  sessions_today: number;
  sessions_yesterday: number;
  pageviews_today: number;
};

export type AnalyticsTimeseries = {
  site_key: string;
  days: number;
  points: Array<{ date: string; pageviews: number; sessions: number }>;
};

export type AnalyticsPages = {
  pages: Array<{ path: string; pageviews: number; sessions: number }>;
};

export type AnalyticsReferrers = {
  referrers: Array<{ source: string; sessions: number }>;
};

export type AnalyticsRecent = {
  hits: Array<{
    id: string;
    path: string;
    session_id: string;
    referrer: string | null;
    utm_source: string | null;
    created_at: string | null;
  }>;
};

export async function apiGetAnalyticsSummary(token: string, days = 30, site = "dlno.ru") {
  return adminGet<AnalyticsSummary>(
    token,
    `/v1/admin/analytics/summary?days=${days}&site=${encodeURIComponent(site)}`,
  );
}

export async function apiGetAnalyticsTimeseries(token: string, days = 30, site = "dlno.ru") {
  return adminGet<AnalyticsTimeseries>(
    token,
    `/v1/admin/analytics/timeseries?days=${days}&site=${encodeURIComponent(site)}`,
  );
}

export async function apiGetAnalyticsPages(token: string, days = 30, site = "dlno.ru") {
  return adminGet<AnalyticsPages>(
    token,
    `/v1/admin/analytics/pages?days=${days}&site=${encodeURIComponent(site)}`,
  );
}

export async function apiGetAnalyticsReferrers(token: string, days = 30, site = "dlno.ru") {
  return adminGet<AnalyticsReferrers>(
    token,
    `/v1/admin/analytics/referrers?days=${days}&site=${encodeURIComponent(site)}`,
  );
}

export async function apiGetAnalyticsRecent(token: string, site = "dlno.ru") {
  return adminGet<AnalyticsRecent>(
    token,
    `/v1/admin/analytics/recent?site=${encodeURIComponent(site)}&limit=40`,
  );
}

export { API_URL };
