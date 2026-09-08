import { NextRequest } from "next/server";

const tenantSlug = process.env.DELNO_TENANT_SLUG || "delno-demo";

function apiBase() {
  return (process.env.DELNO_API_URL || process.env.NEXT_PUBLIC_DELNO_API_URL || "").replace(/\/$/, "");
}

async function proxyTo(path: string, payload: Record<string, unknown>) {
  const base = apiBase();
  if (!base) {
    return Response.json({ error: "DELNO_API_URL not set" }, { status: 503 });
  }

  const response = await fetch(`${base}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-Slug": tenantSlug,
    },
    body: JSON.stringify(payload),
  });

  const detail = await response.text();
  if (!response.ok) {
    return Response.json(
      { error: "DELNO_WIDGET_PROXY_FAILED", detail: detail.slice(0, 500) },
      { status: response.status },
    );
  }

  return Response.json(JSON.parse(detail), {
    headers: { "Cache-Control": "no-store" },
  });
}

/** Gateway: ?action=session|visitor or body.action */
export async function POST(req: NextRequest) {
  const action = req.nextUrl.searchParams.get("action");

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return Response.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const resolved = action || (typeof body.action === "string" ? body.action : "");

  if (resolved === "session") {
    return proxyTo("/v1/public/widget/session", {
      site_key: body.site_key || "demo_dlno",
      visitor_id: body.visitor_id || null,
      page_url: body.page_url || null,
      referrer: body.referrer || null,
      channel: body.channel || "web",
    });
  }

  if (resolved === "visitor") {
    if (!body.session_id) {
      return Response.json({ error: "session_id required" }, { status: 400 });
    }
    if (!body.name && !body.phone) {
      return Response.json({ error: "name or phone required" }, { status: 400 });
    }
    return proxyTo("/v1/public/widget/visitor", {
      site_key: body.site_key || "demo_dlno",
      session_id: body.session_id,
      visitor_id: body.visitor_id || null,
      name: body.name || null,
      phone: body.phone || null,
    });
  }

  return Response.json({ error: "Unknown action; use ?action=session or ?action=visitor" }, { status: 400 });
}
