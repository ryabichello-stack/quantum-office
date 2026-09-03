import { NextRequest } from "next/server";

type WidgetBody = {
  site_key?: string;
  session_id?: string | null;
  visitor_id?: string | null;
  message?: string;
  name?: string | null;
  phone?: string | null;
  page_url?: string | null;
  referrer?: string | null;
  visitor?: {
    name?: string | null;
    phone?: string | null;
    page_url?: string | null;
    referrer?: string | null;
  };
  channel?: string;
};

function apiBase() {
  return (process.env.DELNO_API_URL || process.env.NEXT_PUBLIC_DELNO_API_URL || "").replace(/\/$/, "");
}

const tenantSlug = process.env.DELNO_TENANT_SLUG || "delno-demo";

async function proxyWidget(path: string, payload: Record<string, unknown>) {
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
      { error: "DELNO_WIDGET_FAILED", detail: detail.slice(0, 500) },
      { status: response.status },
    );
  }

  return Response.json(JSON.parse(detail), {
    headers: { "Cache-Control": "no-store" },
  });
}

export async function POST(req: NextRequest) {
  const action = req.nextUrl.searchParams.get("action");

  let body: WidgetBody;
  try {
    body = (await req.json()) as WidgetBody;
  } catch {
    return Response.json({ error: "Invalid JSON" }, { status: 400 });
  }

  if (action === "session") {
    try {
      return await proxyWidget("/v1/public/widget/session", {
        site_key: body.site_key || "demo_dlno",
        visitor_id: body.visitor_id || null,
        page_url: body.page_url || body.visitor?.page_url || null,
        referrer: body.referrer || body.visitor?.referrer || null,
        channel: body.channel || "web",
      });
    } catch (err) {
      const messageText = err instanceof Error ? err.message : "fetch failed";
      return Response.json({ error: "DELNO_API_UNREACHABLE", detail: messageText }, { status: 502 });
    }
  }

  if (action === "visitor") {
    if (!body.session_id) {
      return Response.json({ error: "session_id required" }, { status: 400 });
    }
    const name = body.name ?? body.visitor?.name;
    const phone = body.phone ?? body.visitor?.phone;
    if (!name && !phone) {
      return Response.json({ error: "name or phone required" }, { status: 400 });
    }
    try {
      return await proxyWidget("/v1/public/widget/visitor", {
        site_key: body.site_key || "demo_dlno",
        session_id: body.session_id,
        visitor_id: body.visitor_id || null,
        name: name || null,
        phone: phone || null,
      });
    } catch (err) {
      const messageText = err instanceof Error ? err.message : "fetch failed";
      return Response.json({ error: "DELNO_API_UNREACHABLE", detail: messageText }, { status: 502 });
    }
  }

  const message = (body.message || "").trim();
  if (!message) {
    return Response.json({ error: "message required" }, { status: 400 });
  }

  try {
    return await proxyWidget("/v1/public/widget/message", {
      site_key: body.site_key || "demo_dlno",
      session_id: body.session_id || null,
      visitor_id: body.visitor_id || null,
      message,
      visitor: body.visitor || {},
      channel: body.channel || "web",
    });
  } catch (err) {
    const messageText = err instanceof Error ? err.message : "fetch failed";
    return Response.json({ error: "DELNO_API_UNREACHABLE", detail: messageText }, { status: 502 });
  }
}
