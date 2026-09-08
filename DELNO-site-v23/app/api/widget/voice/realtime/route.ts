import { NextRequest } from "next/server";

export const maxDuration = 120;

const tenantSlug = process.env.DELNO_TENANT_SLUG || "delno-demo";
const siteKey = process.env.NEXT_PUBLIC_DELNO_WIDGET_SITE_KEY || "demo_dlno";

function apiBase() {
  return (process.env.DELNO_API_URL || process.env.NEXT_PUBLIC_DELNO_API_URL || "").replace(/\/$/, "");
}

/** OpenAI Realtime WebRTC — proxy SDP offer to delno-api unified Realtime endpoint. */
export async function POST(req: NextRequest) {
  const base = apiBase();
  if (!base) {
    return new Response("DELNO_API_URL not set", { status: 503 });
  }

  const sdpOffer = await req.text();
  if (!sdpOffer.trim()) {
    return new Response("SDP required", { status: 400 });
  }

  const params = new URLSearchParams({ site_key: siteKey });
  const sessionId = req.nextUrl.searchParams.get("session_id");
  const visitorId = req.nextUrl.searchParams.get("visitor_id");
  if (sessionId) params.set("session_id", sessionId);
  if (visitorId) params.set("visitor_id", visitorId);

  const upstream = await fetch(`${base}/v1/public/widget/voice/realtime?${params}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/sdp",
      "X-Tenant-Slug": tenantSlug,
    },
    body: sdpOffer,
    signal: AbortSignal.timeout(85000),
  });

  const detail = await upstream.text();
  if (!upstream.ok) {
    return new Response(detail.slice(0, 500), { status: upstream.status });
  }

  return new Response(detail, {
    status: 200,
    headers: { "Content-Type": "application/sdp", "Cache-Control": "no-store" },
  });
}
