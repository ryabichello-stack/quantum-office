/** Build a visible thinking / tool chain from an operator chat response. */

export type ThinkingStep = {
  label: string;
  detail?: string;
  ok?: boolean;
};

const ENGINE_LABELS: Record<string, string> = {
  diy_channel_chooser: "Выбираю способ подключения канала",
  diy_channel_bot_path: "Готовлю путь бота и безопасную форму",
  diy_channel_qr: "Запускаю QR-сессию канала",
  diy_credential_form: "Открываю безопасную форму секрета",
  diy_generate_image: "Генерирую изображение",
  diy_calendar_slots: "Смотрю свободные слоты календаря",
  diy_create_conference: "Создаю видеовстречу",
  diy_send_mail_draft: "Готовлю письмо",
  diy_hermes_health: "Проверяю здоровье офиса",
  diy_crm_funnel: "Смотрю CRM-воронку",
  diy_phones_list: "Смотрю список номеров",
  diy_calls_list: "Смотрю историю звонков",
  diy_telephony_script: "Работаю со сценарием Ava",
  diy_billing_summary: "Считаю биллинг",
  diy_get_knowledge: "Ищу в базе знаний",
  diy_hermes_capabilities: "Проверяю готовность коннекторов",
  diy_files_cloud_status: "Смотрю статус облаков",
  diy_web_research: "Открываю сайт в браузере Hermes",
  nous_hermes_agent: "Думаю через Hermes Agent",
  diy_llm: "Формирую ответ",
};

function toolLabel(tool: string): string {
  const map: Record<string, string> = {
    "credentials.open_form": "Открываю форму секрета",
    "channel.chooser": "Спрашиваю способ подключения",
    "channels.qr.start": "Стартую QR",
    "files.cloud_status": "Проверяю облака",
    "hermes.health": "Health офиса",
    "hermes.capabilities": "Коннекторы",
    "crm.funnel": "Воронка CRM",
    "phones.list": "Номера",
    "calls.list": "Звонки",
    "billing.summary": "Биллинг",
    get_knowledge: "База знаний",
    generate_image: "Картинка",
    suggest_calendar_slots: "Слоты календаря",
    create_conference: "Встреча",
    send_mail_draft: "Письмо",
    "telephony.script_get": "Читаю сценарий",
    "telephony.script_propose": "Черновик сценария",
    "telephony.script_save": "Сохраняю сценарий",
    "web.search": "Ищу в открытом интернете",
    "web.fetch": "Скачиваю страницу",
    "web.browse": "Захожу на страницу в браузере",
    "web.research": "Исследую сайт в браузере",
  };
  return map[tool] || `Инструмент: ${tool}`;
}

/** Progressive placeholder thoughts while the request is in flight. */
export function liveThinkingPlan(message: string): ThinkingStep[] {
  const low = (message || "").toLowerCase();
  const steps: ThinkingStep[] = [{ label: "Читаю запрос" }];
  if (/https?:\/\//.test(low) || /зайди|открой сайт|проскан|изучи сайт|instagram|инстаграм|t\.me/.test(low)) {
    steps.push({ label: "Открываю ссылку в браузере Hermes" });
    steps.push({ label: "Снимаю текст со страниц" });
    steps.push({ label: "Собираю комплексный ответ по фактам с сайта" });
    return steps;
  }
  if (/телеграм|telegram|макс|max\b|бот|qr/.test(low)) {
    steps.push({ label: "Смотрю каналы и способ подключения" });
  } else if (/почт|mail|письм|smtp|imap/.test(low)) {
    steps.push({ label: "Проверяю почтовый коннектор" });
  } else if (/календар|слот|встреч|telemost|конферен/.test(low)) {
    steps.push({ label: "Смотрю календарь и встречи" });
  } else if (/файл|диск|облак|yadisk|gdrive|onedrive/.test(low)) {
    steps.push({ label: "Проверяю файлы и облака" });
  } else if (/звон|телефон|sip|ava|скрипт|сценари/.test(low)) {
    steps.push({ label: "Смотрю телефонию и сценарий" });
  } else if (/crm|лид|воронк/.test(low)) {
    steps.push({ label: "Смотрю CRM" });
  } else if (/знан|база|документ/.test(low)) {
    steps.push({ label: "Ищу в базе знаний" });
  } else {
    steps.push({ label: "Подбираю нужный инструмент" });
  }
  steps.push({ label: "Готовлю ответ" });
  return steps;
}

export function buildThinkingChain(result: {
  engine?: string | null;
  tool_calls?: unknown[] | null;
  hermes_run?: unknown;
}): ThinkingStep[] {
  const steps: ThinkingStep[] = [];
  const engine = String(result.engine || "").trim();
  if (engine) {
    steps.push({
      label: ENGINE_LABELS[engine] || `Движок: ${engine}`,
    });
  } else {
    steps.push({ label: "Разбираю запрос" });
  }

  const calls = Array.isArray(result.tool_calls) ? result.tool_calls : [];
  for (const raw of calls) {
    if (!raw || typeof raw !== "object") continue;
    const tc = raw as Record<string, unknown>;
    const tool = String(tc.tool || tc.name || "").trim();
    if (!tool) continue;
    const ok = typeof tc.ok === "boolean" ? tc.ok : undefined;
    const bits: string[] = [];
    if (tc.kind) bits.push(String(tc.kind));
    if (tc.channel) bits.push(String(tc.channel));
    if (typeof tc.count === "number") bits.push(`${tc.count}`);
    if (tc.query) bits.push(String(tc.query).slice(0, 80));
    if (tc.url) bits.push(String(tc.url).slice(0, 120));
    if (tc.title) bits.push(`«${String(tc.title).slice(0, 80)}»`);
    if (tc.engine) bits.push(String(tc.engine));
    if (typeof tc.chars === "number" && tc.chars > 0) bits.push(`${tc.chars} симв.`);
    steps.push({
      label: toolLabel(tool),
      detail: bits.length ? bits.join(" · ") : undefined,
      ok,
    });
  }

  const run = result.hermes_run;
  if (run && typeof run === "object") {
    const hr = run as Record<string, unknown>;
    const runObj = (hr.run || hr) as Record<string, unknown>;
    const nestedSteps = hr.steps || runObj.steps;
    if (Array.isArray(nestedSteps)) {
      for (const s of nestedSteps.slice(0, 12)) {
        if (!s || typeof s !== "object") continue;
        const st = s as Record<string, unknown>;
        steps.push({
          label: String(st.safe_summary || st.tool_id || st.kind || "шаг"),
          detail: st.status ? String(st.status) : undefined,
          ok: st.status === "ok" || st.status === "succeeded" || st.status === "done",
        });
      }
    }
  }

  return steps.length ? steps : [{ label: "Формирую ответ" }];
}

/** Flatten steps into a short narrative for Claude-style thinking body. */
export function thinkingNarrative(steps: ThinkingStep[], upTo?: number): string {
  const slice = typeof upTo === "number" ? steps.slice(0, Math.max(1, upTo)) : steps;
  return slice
    .map((s) => (s.detail ? `${s.label} — ${s.detail}` : s.label))
    .join("\n");
}
