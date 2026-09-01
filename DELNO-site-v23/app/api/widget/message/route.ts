import { NextRequest } from "next/server";

type WidgetBody = {
  site_key?: string;
  session_id?: string | null;
  visitor_id?: string | null;
  message?: string;
  visitor?: {
    name?: string | null;
    page_url?: string | null;
    referrer?: string | null;
  };
  channel?: string;
};

export async function POST(req: NextRequest) {
  const apiBase = (process.env.DELNO_API_URL || process.env.NEXT_PUBLIC_DELNO_API_URL || "")
    .replace(/\/$/, "");
  const tenantSlug = process.env.DELNO_TENANT_SLUG || "delno-demo";

  if (!apiBase) {
    return Response.json({ error: "DELNO_API_URL not set" }, { status: 503 });
  }

  let body: WidgetBody;
  try {
    body = (await req.json()) as WidgetBody;
  } catch {
    return Response.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const message = (body.message || "").trim();
  if (!message) {
    return Response.json({ error: "message required" }, { status: 400 });
  }

  try {
    const response = await fetch(`${apiBase}/v1/public/widget/message`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant-Slug": tenantSlug,
      },
      body: JSON.stringify({
        site_key: body.site_key || "demo_dlno",
        session_id: body.session_id || null,
        visitor_id: body.visitor_id || null,
        message,
        visitor: body.visitor || {},
        channel: body.channel || "web",
      }),
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
  } catch (err) {
    const messageText = err instanceof Error ? err.message : "fetch failed";
    return Response.json({ error: "DELNO_API_UNREACHABLE", detail: messageText }, { status: 502 });
  }
}
