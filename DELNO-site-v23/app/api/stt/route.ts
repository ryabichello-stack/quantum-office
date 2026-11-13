export const runtime = "edge";

function jsonError(message: string, status: number) {
  return Response.json({ error: message }, { status });
}

export async function POST(request: Request) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) return jsonError("STT_NOT_CONFIGURED", 503);

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

  const upstream = new FormData();
  const name = file.type.includes("mp4") || file.type.includes("aac") ? "voice.m4a" : "voice.webm";
  upstream.append("file", file, name);
  upstream.append("model", "gpt-4o-mini-transcribe");
  upstream.append("language", "ru");

  const response = await fetch("https://api.openai.com/v1/audio/transcriptions", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}` },
    body: upstream,
  });

  const detail = await response.text();
  if (!response.ok) {
    console.error("DELNO_STT_UPSTREAM_ERROR", { status: response.status, detail: detail.slice(0, 300) });
    return jsonError("STT_FAILED", response.status >= 500 ? 502 : 400);
  }

  let text = "";
  try {
    const payload = JSON.parse(detail) as { text?: string };
    text = (payload.text || "").trim();
  } catch {
    return jsonError("STT_PARSE_FAILED", 502);
  }

  return Response.json({ text }, { headers: { "Cache-Control": "no-store" } });
}
