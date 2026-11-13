/** Build a visible thinking / tool chain from an operator chat response. */

export type ThinkingStep = {
  label: string;
  detail?: string;
  ok?: boolean;
};

const ENGINE_LABELS: Record<string, string> = {
  diy_channel_chooser: "Выбор способа подключения канала",
  diy_channel_bot_path: "Путь бота + безопасная форма",
  diy_channel_qr: "Старт QR-сессии канала",
  diy_credential_form: "Открыл безопасную форму секрета",
  diy_generate_image: "Генерация изображения",
  diy_calendar_slots: "Слоты календаря",
  diy_create_conference: "Создание встречи",
  diy_send_mail_draft: "Черновик письма",
  diy_hermes_health: "Проверка здоровья офиса",
  diy_crm_funnel: "CRM-воронка",
  diy_phones_list: "Список номеров",
  diy_calls_list: "История звонков",
  diy_telephony_script: "Сценарий Ava",
  diy_billing_summary: "Биллинг",
  diy_get_knowledge: "Поиск в базе знаний",
  diy_hermes_capabilities: "Готовность коннекторов",
  diy_files_cloud_status: "Статус облаков",
  nous_hermes_agent: "Hermes Agent (Nous)",
  diy_llm: "Ответ через DIY-цикл",
};

function toolLabel(tool: string): string {
  const map: Record<string, string> = {
    "credentials.open_form": "Открыть форму секрета",
    "channel.chooser": "Спросить способ подключения",
    "channels.qr.start": "Старт QR",
    "files.cloud_status": "Статус облаков",
    "hermes.health": "Health офиса",
    "hermes.capabilities": "Коннекторы",
    "crm.funnel": "Воронка CRM",
    "phones.list": "Номера",
    "calls.list": "Звонки",
    "billing.summary": "Биллинг",
    get_knowledge: "База знаний",
    generate_image: "Картинка",
    suggest_calendar_slots: "Слоты",
    create_conference: "Встреча",
    send_mail_draft: "Письмо",
    "telephony.script_get": "Читать сценарий",
    "telephony.script_propose": "Черновик сценария",
    "telephony.script_save": "Сохранить сценарий",
  };
  return map[tool] || tool;
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
      detail: engine.startsWith("diy_")
        ? "Быстрый путь по намерению (без болтовни мимо инструментов)"
        : engine.includes("nous")
          ? "Полный агентный прогон"
          : undefined,
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
    const rid = runObj.id || hr.run_id || hr.id;
    if (rid) {
      steps.push({ label: "Run Hermes", detail: String(rid).slice(0, 36) });
    }
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

  steps.push({ label: "Ответ готов", ok: true });
  return steps;
}
