/**
 * Pure UI state for the Hermes mic and the thinking trace.
 * The cabinet binds to these shapes; tests lock the transitions.
 */

export type DictatePhase = "idle" | "recording" | "transcribing";

export type DictateSnapshot = {
  phase: DictatePhase;
  error: string;
  elapsedMs: number;
  /** 0..1 microphone energy from AnalyserNode. */
  level: number;
  /** Text already placed in the composer. Not sent automatically. */
  draft: string;
  /** True only after a real streaming engine emitted a partial. */
  streaming: boolean;
};

export type DictateEvent =
  | { type: "start" }
  | { type: "tick"; elapsedMs: number }
  | { type: "level"; level: number }
  | { type: "partial"; text: string }
  | { type: "stop" }
  | { type: "recognized"; text: string }
  | { type: "fail"; message: string }
  | { type: "cancel" }
  | { type: "dismiss-error" };

export function initialDictate(): DictateSnapshot {
  return {
    phase: "idle",
    error: "",
    elapsedMs: 0,
    level: 0,
    draft: "",
    streaming: false,
  };
}

export function reduceDictate(state: DictateSnapshot, event: DictateEvent): DictateSnapshot {
  switch (event.type) {
    case "start":
      if (state.phase !== "idle") return state;
      return {
        ...state,
        phase: "recording",
        error: "",
        elapsedMs: 0,
        level: 0,
        streaming: false,
      };
    case "tick":
      if (state.phase !== "recording") return state;
      return { ...state, elapsedMs: Math.max(0, event.elapsedMs) };
    case "level":
      if (state.phase !== "recording") return state;
      return { ...state, level: Math.min(1, Math.max(0, event.level)) };
    case "partial":
      if (state.phase !== "recording") return state;
      return { ...state, draft: event.text, streaming: true };
    case "stop":
      if (state.phase !== "recording") return state;
      return { ...state, phase: "transcribing", level: 0 };
    case "recognized":
      if (state.phase !== "transcribing") return state;
      return {
        ...state,
        phase: "idle",
        draft: event.text,
        level: 0,
        elapsedMs: 0,
        streaming: false,
        error: "",
      };
    case "fail":
      return {
        ...state,
        phase: "idle",
        error: event.message,
        level: 0,
        elapsedMs: 0,
        streaming: false,
      };
    case "cancel":
      return { ...initialDictate(), draft: state.draft };
    case "dismiss-error":
      return { ...state, error: "" };
    default:
      return state;
  }
}

export function formatRecordTime(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function micButtonLabel(phase: DictatePhase): string {
  if (phase === "recording") return "Остановить запись";
  if (phase === "transcribing") return "Распознаю речь";
  return "Голосовой ввод";
}

const WAVE_SHAPE = [0.45, 0.72, 1, 0.78, 0.5];

/** Bar heights in px. Silence stays short; speech lifts the bars. */
export function waveHeights(level: number, elapsedMs: number): number[] {
  const energy = Math.min(1, Math.max(0, level));
  return WAVE_SHAPE.map((shape, i) => {
    const wobble = 0.72 + 0.28 * Math.sin(elapsedMs / 160 + i * 0.9);
    return Math.round(4 + energy * 18 * shape * wobble);
  });
}

export type ThoughtStep = { label: string; detail?: string };

export type ThinkingView = {
  live: boolean;
  /** One line: the current action, or «Сделал N действий» once the reply is ready. */
  line: string;
  /** Full list, in the same words, shown when the owner opens the row. */
  steps: ThoughtStep[];
};

const ACTION_LABELS: Record<string, string> = {
  "credentials.open_form": "Открываю безопасную форму…",
  "credentials.form": "Открываю безопасную форму…",
  "credentials.save": "Сохраняю секрет…",
  "channel.chooser": "Спрашиваю, как подключить канал…",
  "channels.qr.start": "Запускаю QR-подключение…",
  "files.cloud_status": "Проверяю облачные файлы…",
  "hermes.health": "Проверяю здоровье офиса…",
  "hermes.capabilities": "Проверяю подключения…",
  "hermes.guide": "Подсказываю следующий шаг…",
  "hermes.setup_status": "Смотрю, что осталось настроить…",
  "hermes.templates.download": "Готовлю шаблон…",
  "hermes.agent_run": "Думаю над ответом…",
  "hermes.tasks_create": "Создаю поручение…",
  "hermes.tasks_list": "Смотрю поручения…",
  "hermes.tasks_pause": "Ставлю поручение на паузу…",
  "hermes.tasks_resume": "Возобновляю поручение…",
  "crm.funnel": "Смотрю воронку…",
  "phones.list": "Смотрю номера…",
  "phones.provision": "Привязываю номер…",
  "phones.bind": "Привязываю номер…",
  "phones.attach": "Привязываю номер…",
  "calls.list": "Смотрю звонки…",
  "billing.summary": "Считаю расходы…",
  get_knowledge: "Проверяю базу знаний…",
  get_company_knowledge: "Проверяю базу знаний…",
  upload_knowledge_snippet: "Кладу текст в базу знаний…",
  generate_image: "Генерирую изображение…",
  suggest_calendar_slots: "Смотрю свободное время…",
  check_calendar: "Смотрю календарь…",
  create_conference: "Создаю встречу…",
  send_mail_draft: "Готовлю письмо…",
  "telephony.script_get": "Читаю сценарий звонков…",
  "telephony.script_propose": "Готовлю сценарий звонков…",
  "telephony.script_save": "Сохраняю сценарий звонков…",
  "telephony.tools_set": "Настраиваю телефонию…",
  "web.search": "Ищу в интернете…",
  "web.fetch": "Читаю страницу…",
  "web.browse": "Открываю сайт…",
  "web.research": "Ищу на сайте компании…",
  "office.build_kb_draft": "Собираю черновик базы знаний…",
  llm: "Думаю над ответом…",
  attachments: "Смотрю вложения…",
  set_feature_flag: "Меняю настройку офиса…",
  update_tenant_settings: "Обновляю настройки офиса…",
  get_tenant_summary: "Смотрю настройки офиса…",
  create_lead: "Записываю заявку…",
  diy_channel_chooser: "Выбираю способ подключения…",
  diy_channel_bot_path: "Готовлю подключение бота…",
  diy_channel_qr: "Запускаю QR-подключение…",
  diy_credential_form: "Открываю безопасную форму…",
  diy_generate_image: "Генерирую изображение…",
  diy_calendar_slots: "Смотрю свободное время…",
  diy_create_conference: "Создаю встречу…",
  diy_send_mail_draft: "Готовлю письмо…",
  diy_hermes_health: "Проверяю здоровье офиса…",
  diy_crm_funnel: "Смотрю воронку…",
  diy_phones_list: "Смотрю номера…",
  diy_calls_list: "Смотрю звонки…",
  diy_telephony_script: "Работаю со сценарием звонков…",
  diy_billing_summary: "Считаю расходы…",
  diy_get_knowledge: "Проверяю базу знаний…",
  diy_hermes_capabilities: "Проверяю подключения…",
  diy_files_cloud_status: "Проверяю облачные файлы…",
  diy_web_research: "Ищу на сайте компании…",
  diy_hermes_tasks: "Настраиваю поручение…",
  nous_hermes_agent: "Думаю над ответом…",
  diy_llm: "Думаю над ответом…",
};

const FALLBACK_ACTION = "Выполняю действие…";

function actionKey(raw: string): string {
  return raw
    .replace(/^(инструмент|движок)\s*:\s*/i, "")
    .trim()
    .toLowerCase();
}

function prefixAction(key: string): string | null {
  if (/^phones\.(provision|bind|attach|link)/.test(key)) return "Привязываю номер…";
  if (key.startsWith("phones.")) return "Смотрю номера…";
  if (key.startsWith("credentials.")) return "Открываю безопасную форму…";
  if (key.startsWith("telephony.")) return "Настраиваю телефонию…";
  if (key.startsWith("web.search")) return "Ищу в интернете…";
  if (key.startsWith("web.fetch")) return "Читаю страницу…";
  if (key.startsWith("web.browse")) return "Открываю сайт…";
  if (key.startsWith("web.")) return "Ищу на сайте компании…";
  if (key.includes("knowledge") || key.startsWith("kb.")) return "Проверяю базу знаний…";
  if (key.includes("calendar")) return "Смотрю календарь…";
  if (key.startsWith("mail.") || key.includes("send_mail") || key.includes("smtp") || key.includes("imap")) {
    return "Готовлю письмо…";
  }
  if (key.startsWith("calls.")) return "Смотрю звонки…";
  if (key.startsWith("crm.")) return "Смотрю воронку…";
  if (key.startsWith("billing.")) return "Считаю расходы…";
  if (key.startsWith("files.") || key.includes("yadisk") || key.includes("gdrive") || key.includes("onedrive")) {
    return "Проверяю файлы…";
  }
  if (key.startsWith("hermes.tasks")) return "Настраиваю поручение…";
  if (key.startsWith("channel")) return "Подключаю канал…";
  return null;
}

/** Latin tool ids and engine slugs. Ordinary words and URLs stay. */
export function isTechnicalName(value: string): boolean {
  const v = value.trim();
  if (!v || /^https?:\/\//i.test(v)) return false;
  if (/[А-Яа-яЁё]/.test(v)) return false;
  if (/^[a-z0-9_]+(\.[a-z0-9_]+)+$/i.test(v)) return true;
  if (/^[a-z0-9]+_[a-z0-9_]+$/i.test(v)) return true;
  if (/^(ok|succeeded|done|failed|error|pending|stub_echo)$/i.test(v)) return true;
  return false;
}

/** Present-tense owner wording. Never returns a raw tool id. */
export function humanAction(raw: string | undefined | null): string {
  const text = (raw || "").trim();
  if (!text) return FALLBACK_ACTION;
  const key = actionKey(text);
  if (ACTION_LABELS[key]) return ACTION_LABELS[key];
  const prefixed = prefixAction(key);
  if (prefixed) return prefixed;
  if (isTechnicalName(key) || isTechnicalName(text)) return FALLBACK_ACTION;
  if (/[А-Яа-яЁё]/.test(text)) return text.endsWith("…") ? text : `${text.replace(/[.\s]+$/, "")}…`;
  return FALLBACK_ACTION;
}

export function humanDetail(detail?: string): string | undefined {
  if (!detail) return undefined;
  const kept = detail
    .split(" · ")
    .map((bit) => bit.trim())
    .filter((bit) => {
      if (!bit || isTechnicalName(bit)) return false;
      if (/^https?:\/\//i.test(bit) || /^«/.test(bit) || /[А-Яа-яЁё]/.test(bit) || /^\d+$/.test(bit)) return true;
      return !ACTION_LABELS[actionKey(bit)] && !prefixAction(actionKey(bit));
    });
  return kept.length ? kept.join(" · ") : undefined;
}

function presentStep(step: ThoughtStep): ThoughtStep {
  return { label: humanAction(step.label), detail: humanDetail(step.detail) };
}

export function ruActions(count: number): string {
  const n = Math.abs(Math.trunc(count));
  const n10 = n % 10;
  const n100 = n % 100;
  let word = "действий";
  if (n10 === 1 && n100 !== 11) word = "действие";
  else if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) word = "действия";
  return `${n} ${word}`;
}

export function doneActionsLabel(count: number): string {
  return `Сделал ${ruActions(count)}`;
}

const THINKING_LINE = "Думаю над ответом…";

export type LiveTrace = {
  steps: ThoughtStep[];
  awaiting: boolean;
  seen: string[];
};

export function reduceLiveTrace(
  state: LiveTrace,
  event: { phase?: string; tool?: string; preview?: string; tool_call_id?: string },
): LiveTrace {
  const phase = event.phase || "";
  if (phase === "thinking" || phase === "between") {
    return { ...state, awaiting: true };
  }
  if (phase === "tool") {
    const id = (event.tool_call_id || "").trim();
    if (id && state.seen.includes(id)) return { ...state, awaiting: false };
    const label = humanAction(event.tool || "");
    const detail = event.preview ? humanDetail(event.preview) : undefined;
    return {
      awaiting: false,
      seen: id ? [...state.seen, id] : state.seen,
      steps: [...state.steps, { label, detail }],
    };
  }
  return state;
}

export function thinkingView(
  steps: ThoughtStep[],
  opts: { live?: boolean; liveIndex?: number; awaiting?: boolean },
): ThinkingView {
  const live = Boolean(opts.live);
  const readyAll = steps.map(presentStep);
  if (!live) {
    if (!readyAll.length) return { live: false, line: "", steps: [] };
    return { live: false, line: doneActionsLabel(readyAll.length), steps: readyAll };
  }
  if (!readyAll.length || opts.awaiting) {
    const visible = opts.liveIndex ? readyAll.slice(0, Math.max(0, opts.liveIndex)) : readyAll;
    return { live: true, line: THINKING_LINE, steps: visible.length ? visible : readyAll };
  }
  const visible = readyAll.slice(0, Math.max(1, opts.liveIndex || readyAll.length));
  const current = visible[visible.length - 1];
  return {
    live: true,
    line: current?.label || THINKING_LINE,
    steps: visible,
  };
}
