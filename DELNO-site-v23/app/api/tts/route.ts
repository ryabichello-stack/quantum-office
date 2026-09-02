import { demoAnswers, type DemoAnswerId } from "../../v2/demoContent";

export const runtime = "edge";

const TTS_INSTRUCTIONS =
  "Говори на чистом естественном русском языке. Голос мягкий, уверенный, современный и доброжелательный, как у премиального бизнес-помощника. Средний темп, живые интонации, без театральности, пафоса и рекламного нажима.";

function jsonError(message: string, status: number) {
  return Response.json({ error: message }, { status });
}

export async function GET(request: Request) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) return jsonError("VOICE_NOT_CONFIGURED", 503);

  const url = new URL(request.url);
  const textParam = (url.searchParams.get("text") || "").trim();
  const answerIdParam = url.searchParams.get("answerId");

  let input = textParam;
  if (!input && answerIdParam && answerIdParam in demoAnswers) {
    input = demoAnswers[answerIdParam as DemoAnswerId];
  }
  if (!input) return jsonError("TEXT_REQUIRED", 400);
  if (input.length > 800) input = input.slice(0, 800);

  const response = await fetch("https://api.openai.com/v1/audio/speech", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "gpt-4o-mini-tts",
      voice: "marin",
      input,
      instructions: TTS_INSTRUCTIONS,
      response_format: "mp3",
    }),
  });

  if (!response.ok || !response.body) {
    const details = await response.text().catch(() => "");
    console.error("DELNO_TTS_UPSTREAM_ERROR", {
      status: response.status,
      details: details.slice(0, 300),
    });
    if (response.status === 401 || response.status === 403) return jsonError("VOICE_AUTH_FAILED", 502);
    if (response.status === 429) return jsonError("VOICE_LIMIT_REACHED", 503);
    return jsonError("VOICE_GENERATION_FAILED", 502);
  }

  return new Response(response.body, {
    headers: {
      "Content-Type": "audio/mpeg",
      "Cache-Control": "public, max-age=86400, s-maxage=604800, immutable",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
