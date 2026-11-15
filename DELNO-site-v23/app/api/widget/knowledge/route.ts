import { NextRequest } from "next/server";

const tenantSlug = process.env.DELNO_TENANT_SLUG || "delno-demo";
const siteKey = process.env.NEXT_PUBLIC_DELNO_WIDGET_SITE_KEY || "demo_dlno";

function apiBase() {
  return (process.env.DELNO_API_URL || process.env.NEXT_PUBLIC_DELNO_API_URL || "").replace(/\/$/, "");
}

/** KB search for Realtime get_knowledge tool (browser executes, server searches Second Brain). */
export async function POST(req: NextRequest) {
  const base = apiBase();
  if (!base) {
    return new Response("DELNO_API_URL not set", { status: 503 });
  }

  let body: { query?: string; site_key?: string };
  try {
    body = (await req.json()) as { query?: string; site_key?: string };
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }

  const query = (body.query || "").trim();
  if (!query) {
    return new Response("query required", { status: 400 });
  }

  const upstream = await fetch(`${base}/v1/public/widget/knowledge`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-Slug": tenantSlug,
    },
    body: JSON.stringify({
      site_key: body.site_key || siteKey,
      query,
    }),
  });

  const detail = await upstream.text();
  return new Response(detail, {
    status: upstream.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}
