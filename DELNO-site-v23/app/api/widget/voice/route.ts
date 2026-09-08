import { prepareTtsText } from "@/lib/ttsText";

export const runtime = "edge";

const SITE_KEY = process.env.NEXT_PUBLIC_DELNO_WIDGET_SITE_KEY || "demo_dlno";
const tenantSlug = process.env.DELNO_TENANT_SLUG || "delno-demo";

function apiBase() {
  return (process.env.DELNO_API_URL || process.env.NEXT_PUBLIC_DELNO_API_URL || "").replace(/\/$/, "");
}

function jsonError(message: string, status: number) {
  return Response.json({ error: message }, { status });
}

async function transcribe(apiKey: string, file: Blob, fileName: string) {
  const upstream = new FormData();
  upstream.append("file", file, fileName);
  upstream.append("model", "gpt-4o-mini-transcribe");
  upstream.append("language", "ru");

  const response = await fetch("https://api.openai.com/v1/audio/transcriptions", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}` },
    body: upstream,
  });

  const detail = await response.text();
  if (!response.ok) {
    console.error("DELNO_VOICE_STT_ERROR", response.status, detail.slice(0, 200));
    throw new Error("stt_failed");
  }

  const payload = JSON.parse(detail) as { text?: string };
  return (payload.text || "").trim();
}

async function askWidget(body: Record<string, unknown>) {
  const base = apiBase();
  if (!base) throw new Error("api_not_configured");

  const response = await fetch(`${base}/v1/public/widget/message`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-Slug": tenantSlug,
    },
    body: JSON.stringify(body),
  });

  const detail = await response.text();
  if (!response.ok) {
    throw new Error(detail.slice(0, 200) || "widget_failed");
  }

  return JSON.parse(detail) as { message?: string; conversation_id?: string };
}

export async function POST(request: Request) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) return jsonError("VOICE_NOT_CONFIGURED", 503);

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return jsonError("Invalid form data", 400);
  }

  const file = form.get("file");
  if (!file || !(file instanceof Blob) || file.size < 200) {
    return jsonError("file required", 400);
  }

  const siteKey = String(form.get("site_key") || SITE_KEY);
  const visitorId = String(form.get("visitor_id") || "");
  const sessionId = form.get("session_id") ? String(form.get("session_id")) : null;
  const pageUrl = form.get("page_url") ? String(form.get("page_url")) : null;

  const fileName =
    file.type.includes("mp4") || file.type.includes("aac") ? "voice.m4a" : "voice.webm";

  let transcript = "";
  try {
    transcript = await transcribe(apiKey, file, fileName);
  } catch {
    return jsonError("STT_FAILED", 502);
  }

  if (!transcript) {
    return jsonError("EMPTY_TRANSCRIPT", 400);
  }

  try {
    const answer = await askWidget({
      site_key: siteKey,
      session_id: sessionId,
      visitor_id: visitorId || null,
      message: transcript,
      visitor: { page_url: pageUrl },
      channel: "web",
      input_modality: "voice",
    });

    return Response.json(
      {
        transcript,
        message: answer.message || "",
        conversation_id: answer.conversation_id,
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (err) {
    const detail = err instanceof Error ? err.message : "widget_failed";
    return jsonError(detail, 502);
  }
}
