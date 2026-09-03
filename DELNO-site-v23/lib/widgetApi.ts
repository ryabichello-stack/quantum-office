import { prepareTtsText } from "./ttsText";

const SITE_KEY = process.env.NEXT_PUBLIC_DELNO_WIDGET_SITE_KEY || "demo_dlno";

export function getBasePath() {
  return process.env.NEXT_PUBLIC_BASE_PATH || "";
}

export function widgetMessagePath() {
  return `${getBasePath()}/api/widget/message`;
}

export function widgetTtsPath(text: string) {
  const q = encodeURIComponent(prepareTtsText(text).slice(0, 800));
  return `${getBasePath()}/api/tts?text=${q}`;
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

const WIDGET_FETCH_MS = 25000;

export async function askDelnoWidget(message: string): Promise<{ answer: string; error?: string }> {
  const value = message.trim();
  if (!value) return { answer: "", error: "empty" };

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), WIDGET_FETCH_MS);

  try {
    const res = await fetch(widgetMessagePath(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        site_key: SITE_KEY,
        session_id: getSessionId(),
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
      return { answer: "", error: detail || `HTTP ${res.status}` };
    }

    const payload = JSON.parse(raw) as { message?: string; conversation_id?: string };
    if (payload.conversation_id) persistSession(payload.conversation_id);
    return { answer: payload.message || "" };
  } catch (err) {
    const msg =
      err instanceof Error && err.name === "AbortError"
        ? "Превышено время ожидания ответа"
        : err instanceof Error
          ? err.message
          : "fetch failed";
    return { answer: "", error: msg };
  } finally {
    window.clearTimeout(timer);
  }
}
