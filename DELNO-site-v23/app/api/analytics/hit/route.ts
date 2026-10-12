export const runtime = "nodejs";

type HitPayload = {
  site_key?: unknown;
  session_id?: unknown;
  path?: unknown;
  referrer?: unknown;
  title?: unknown;
  utm_source?: unknown;
  utm_medium?: unknown;
  utm_campaign?: unknown;
  event?: unknown;
  duration_ms?: unknown;
  engaged?: unknown;
};

const clean = (value: unknown, max = 200) =>
  typeof value === "string" ? value.trim().slice(0, max) : "";

export async function POST(request: Request) {
  const apiBase = (process.env.DELNO_API_URL || process.env.NEXT_PUBLIC_DELNO_API_URL || "")
    .replace(/\/$/, "");
  if (!apiBase) {
    return Response.json({ ok: true, skipped: "no_api" });
  }

  let input: HitPayload;
  try {
    input = (await request.json()) as HitPayload;
  } catch {
    return Response.json({ error: "INVALID_JSON" }, { status: 400 });
  }

  const session_id = clean(input.session_id, 64);
  const path = clean(input.path, 512);
  if (!session_id || session_id.length < 8 || !path) {
    return Response.json({ error: "INVALID_HIT" }, { status: 400 });
  }

  const body = {
    site_key: clean(input.site_key, 64) || process.env.NEXT_PUBLIC_ANALYTICS_SITE_KEY || "dlno.ru",
    session_id,
    path: path.startsWith("/") ? path : `/${path}`,
    referrer: clean(input.referrer, 1000) || undefined,
    title: clean(input.title, 255) || undefined,
    utm_source: clean(input.utm_source, 120) || undefined,
    utm_medium: clean(input.utm_medium, 120) || undefined,
    utm_campaign: clean(input.utm_campaign, 160) || undefined,
    event: clean(input.event, 32) || "pageview",
    duration_ms:
      typeof input.duration_ms === "number" && Number.isFinite(input.duration_ms)
        ? Math.max(0, Math.min(Math.floor(input.duration_ms), 86_400_000))
        : undefined,
    engaged: Boolean(input.engaged),
  };

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`${apiBase}/v1/public/analytics/hit`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Forwarded-For": request.headers.get("x-forwarded-for") || "",
        "User-Agent": request.headers.get("user-agent") || "",
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      return Response.json(
        { error: "ANALYTICS_UPSTREAM", detail: detail.slice(0, 300) },
        { status: response.status === 429 ? 429 : 502 },
      );
    }
    return Response.json({ ok: true });
  } catch (err) {
    clearTimeout(timeout);
    const message = err instanceof Error ? err.message : "network_error";
    return Response.json({ error: "ANALYTICS_UNREACHABLE", detail: message }, { status: 502 });
  }
}
