import { prepareTtsText } from "./ttsText";

const SITE_KEY = process.env.NEXT_PUBLIC_DELNO_WIDGET_SITE_KEY || "demo_dlno";

export function getBasePath() {
  return process.env.NEXT_PUBLIC_BASE_PATH || "";
}

export function widgetMessagePath() {
  return `${getBasePath()}/api/widget/message`;
}

export function widgetGatewayPath(action: "session" | "visitor") {
  return `${getBasePath()}/api/widget?action=${action}`;
}

export function widgetTtsPath(text: string) {
  const q = encodeURIComponent(prepareTtsText(text).slice(0, 800));
  return `${getBasePath()}/api/tts?text=${q}`;
}

export function widgetSttPath() {
  return `${getBasePath()}/api/stt`;
}

export function widgetVoicePath() {
  return `${getBasePath()}/api/widget/voice`;
}

export function widgetRealtimePath() {
  const params = new URLSearchParams({
    site_key: SITE_KEY,
    visitor_id: getVisitorId(),
  });
  const sessionId = getSessionId();
  if (sessionId) params.set("session_id", sessionId);
  return `${getBasePath()}/api/widget/voice/realtime?${params}`;
}

export function widgetKnowledgePath() {
  return `${getBasePath()}/api/widget/knowledge`;
}

function cryptoSafeId() {
  try {
    if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  } catch {
    /* ignore */
  }
  return `w_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

function getVisitorId() {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem("delno_widget_visitor");
  if (!id) {
    id = cryptoSafeId();
    localStorage.setItem("delno_widget_visitor", id);
  }
  return id;
}

function getSessionId() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("delno_widget_session");
}

function persistSession(id: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem("delno_widget_session", id);
}

/** Widget message round-trip — allow slow LLM + KB on cold starts. */
export const WIDGET_FETCH_MS = 90000;

export type WidgetMessagePayload = {
  message?: string;
  conversation_id?: string;
  next_step?: string;
  sources?: unknown[];
  lead?: { id?: string; name?: string; phone?: string } | null;
};

function widgetFetchError(err: unknown): string {
  if (err instanceof Error && err.name === "AbortError") {
    return "Превышено время ожидания ответа. Попробуйте ещё раз.";
  }
  return err instanceof Error ? err.message : "fetch failed";
}

export async function postWidgetMessage(
  message: string,
  options?: { sessionId?: string | null; signal?: AbortSignal },
): Promise<{ payload: WidgetMessagePayload | null; error?: string }> {
  const value = message.trim();
  if (!value) return { payload: null, error: "empty" };

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), WIDGET_FETCH_MS);
  const onParentAbort = () => controller.abort();
  options?.signal?.addEventListener("abort", onParentAbort, { once: true });

  try {
    const res = await fetch(widgetMessagePath(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        site_key: SITE_KEY,
        session_id: options?.sessionId ?? getSessionId(),
        visitor_id: getVisitorId(),
        message: value,
        visitor: {
          name: localStorage.getItem("delno_widget_name") || null,
          page_url: window.location.href,
          referrer: document.referrer || null,
        },
        channel: "web",
      }),
    });

    const raw = await res.text();
    if (!res.ok) {
      let detail = raw.slice(0, 200);
      try {
        const parsed = JSON.parse(raw) as { error?: string; detail?: string };
        detail = parsed.detail || parsed.error || detail;
      } catch {
        /* ignore */
      }
      return { payload: null, error: detail || `HTTP ${res.status}` };
    }

    const payload = JSON.parse(raw) as WidgetMessagePayload;
    if (payload.conversation_id) persistSession(payload.conversation_id);
    return { payload };
  } catch (err) {
    return { payload: null, error: widgetFetchError(err) };
  } finally {
    window.clearTimeout(timer);
    options?.signal?.removeEventListener("abort", onParentAbort);
  }
}

export async function askDelnoWidget(message: string): Promise<{ answer: string; error?: string }> {
  const { payload, error } = await postWidgetMessage(message);
  return { answer: payload?.message || "", error };
}

export async function askDelnoVoice(audio: Blob, mime: string): Promise<{
  transcript: string;
  answer: string;
  error?: string;
}> {
  const form = new FormData();
  const ext = mime.includes("mp4") || mime.includes("aac") ? "m4a" : "webm";
  form.append("file", audio, `voice.${ext}`);
  form.append("site_key", SITE_KEY);
  form.append("visitor_id", getVisitorId());
  const sessionId = getSessionId();
  if (sessionId) form.append("session_id", sessionId);
  if (typeof window !== "undefined") form.append("page_url", window.location.href);

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), WIDGET_FETCH_MS);

  try {
    const res = await fetch(widgetVoicePath(), { method: "POST", body: form, signal: controller.signal });
    const raw = await res.text();
    if (!res.ok) {
      return { transcript: "", answer: "", error: raw.slice(0, 200) || `HTTP ${res.status}` };
    }
    const payload = JSON.parse(raw) as { transcript?: string; message?: string; conversation_id?: string };
    if (payload.conversation_id) persistSession(payload.conversation_id);
    return {
      transcript: (payload.transcript || "").trim(),
      answer: (payload.message || "").trim(),
    };
  } catch (err) {
    const msg =
      err instanceof Error && err.name === "AbortError"
        ? "Превышено время ожидания ответа"
        : err instanceof Error
          ? err.message
          : "fetch failed";
    return { transcript: "", answer: "", error: msg };
  } finally {
    window.clearTimeout(timer);
  }
}
