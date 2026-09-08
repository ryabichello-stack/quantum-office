export const runtime = "nodejs";

type SuggestPayload = {
  q?: unknown;
  count?: unknown;
};

const cleanQuery = (value: unknown) =>
  typeof value === "string" ? value.trim().slice(0, 120) : "";

export async function POST(request: Request) {
  const apiBase = (process.env.DELNO_API_URL || process.env.NEXT_PUBLIC_DELNO_API_URL || "").replace(
    /\/$/,
    "",
  );
  const tenantSlug = process.env.DELNO_TENANT_SLUG || "delno-demo";

  if (!apiBase) {
    return Response.json({ error: "DELNO_API_URL not set" }, { status: 503 });
  }

  let input: SuggestPayload;
  try {
    input = (await request.json()) as SuggestPayload;
  } catch {
    return Response.json({ error: "INVALID_JSON" }, { status: 400 });
  }

  const q = cleanQuery(input.q);
  if (q.length < 2) {
    return Response.json({ error: "QUERY_TOO_SHORT" }, { status: 400 });
  }

  const countRaw = typeof input.count === "number" ? input.count : Number(input.count);
  const count = Number.isFinite(countRaw) ? Math.min(10, Math.max(1, Math.floor(countRaw))) : 5;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(`${apiBase}/v1/public/party/suggest`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant-Slug": tenantSlug,
      },
      body: JSON.stringify({ q, count }),
      signal: controller.signal,
    });
    clearTimeout(timeout);

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return Response.json(
        { error: "PARTY_SUGGEST_FAILED", detail: JSON.stringify(data).slice(0, 500) },
        { status: response.status >= 500 ? 502 : response.status },
      );
    }

    return Response.json(data, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (err) {
    clearTimeout(timeout);
    const message = err instanceof Error ? err.message : "network_error";
    return Response.json({ error: "DELNO_API_UNREACHABLE", detail: message }, { status: 502 });
  }
}
