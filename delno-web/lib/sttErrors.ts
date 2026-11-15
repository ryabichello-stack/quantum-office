/**
 * Owner-facing copy for mic / speech-to-text failures.
 * Raw engine codes (STT_FAILED and the like) must never reach the cabinet.
 */

const MESSAGES: Record<string, string> = {
  "not-allowed": "Нет доступа к микрофону — разрешите его в настройках браузера.",
  "service-not-allowed": "Нет доступа к микрофону — разрешите его в настройках браузера.",
  NotAllowedError: "Нет доступа к микрофону — разрешите его в настройках браузера.",
  SecurityError: "Нет доступа к микрофону — разрешите его в настройках браузера.",
  "audio-capture": "Микрофон недоступен. Проверьте, что устройство подключено.",
  NotFoundError: "Микрофон недоступен. Проверьте, что устройство подключено.",
  NotReadableError: "Микрофон недоступен. Проверьте, что устройство подключено.",
  network: "Не удалось распознать речь. Проверьте соединение и попробуйте ещё раз.",
  STT_FAILED: "Не удалось распознать речь. Попробуйте ещё раз.",
  STT_NOT_CONFIGURED: "Распознавание речи сейчас недоступно. Напишите сообщение текстом.",
  STT_AUTH_FAILED: "Распознавание речи сейчас недоступно. Напишите сообщение текстом.",
  STT_LIMIT_REACHED: "Сервис распознавания перегружен. Попробуйте чуть позже.",
  STT_EMPTY: "Речь не распознана. Говорите чуть дольше и нажмите «Стоп».",
  "no-speech": "Речь не распознана. Говорите чуть дольше и нажмите «Стоп».",
  AUDIO_TOO_LARGE: "Запись слишком длинная. Попробуйте сказать короче.",
  AUDIO_REQUIRED: "Запись пустая. Нажмите микрофон и говорите.",
  "no-session": "Нет сессии для распознавания речи. Обновите страницу и войдите снова.",
  unsupported: "Микрофон недоступен в этом браузере.",
};

const BENIGN = new Set(["aborted", "interrupted"]);

export function isBenignSttError(code?: string): boolean {
  return BENIGN.has((code || "").trim());
}

/** Always a Russian sentence. Unknown codes collapse to a generic sentence. */
export function sttErrorMessage(code?: string): string {
  const key = (code || "").trim();
  if (key && MESSAGES[key]) return MESSAGES[key];
  return "Не удалось распознать речь. Попробуйте ещё раз.";
}
