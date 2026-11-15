/** Build a visible thinking / tool chain from an operator chat response. */

import { humanAction, humanDetail } from "@/lib/hermesUiStates";

export type ThinkingStep = {
  label: string;
  detail?: string;
  ok?: boolean;
};

function remember(steps: ThinkingStep[], step: ThinkingStep) {
  const label = humanAction(step.label);
  const last = steps[steps.length - 1];
  if (last && last.label === label) return;
  steps.push({ ...step, label, detail: humanDetail(step.detail) });
}

/** Progressive placeholder thoughts while the request is in flight. */
export function liveThinkingPlan(message: string): ThinkingStep[] {
  const low = (message || "").toLowerCase();
  const steps: ThinkingStep[] = [{ label: "Читаю запрос…" }];
  if (/кажд|расписан|поручен|периодическ|ежеднев|ежечас/.test(low)) {
    steps.push({ label: "Разбираю расписание…" });
    steps.push({ label: "Настраиваю поручение…" });
    return steps;
  }
  if (/https?:\/\//.test(low) || /зайди|открой сайт|проскан|изучи сайт|instagram|инстаграм|t\.me/.test(low)) {
    steps.push({ label: "Открываю сайт…" });
    steps.push({ label: "Читаю страницу…" });
    steps.push({ label: "Ищу на сайте компании…" });
    return steps;
  }
  if (/телеграм|telegram|макс|max\b|бот|qr/.test(low)) {
    steps.push({ label: "Смотрю, как подключить канал…" });
  } else if (/почт|mail|письм|smtp|imap/.test(low)) {
    steps.push({ label: "Проверяю почту…" });
  } else if (/календар|слот|встреч|telemost|конферен/.test(low)) {
    steps.push({ label: "Смотрю календарь…" });
  } else if (/файл|диск|облак|yadisk|gdrive|onedrive/.test(low)) {
    steps.push({ label: "Проверяю файлы…" });
  } else if (/звон|телефон|sip|ava|скрипт|сценари/.test(low)) {
    steps.push({ label: "Проверяю телефонию…" });
  } else if (/crm|лид|воронк/.test(low)) {
    steps.push({ label: "Смотрю воронку…" });
  } else if (/знан|база|документ/.test(low)) {
    steps.push({ label: "Проверяю базу знаний…" });
  } else {
    steps.push({ label: "Подбираю, что сделать…" });
  }
  steps.push({ label: "Думаю над ответом…" });
  return steps;
}

export function buildThinkingChain(result: {
  engine?: string | null;
  tool_calls?: unknown[] | null;
  hermes_run?: unknown;
}): ThinkingStep[] {
  const steps: ThinkingStep[] = [];
  const engine = String(result.engine || "").trim();
  remember(steps, { label: engine ? engine : "Читаю запрос…" });

  const calls = Array.isArray(result.tool_calls) ? result.tool_calls : [];
  for (const raw of calls) {
    if (!raw || typeof raw !== "object") continue;
    const tc = raw as Record<string, unknown>;
    const tool = String(tc.tool || tc.name || "").trim();
    if (!tool) continue;
    const ok = typeof tc.ok === "boolean" ? tc.ok : undefined;
    const bits: string[] = [];
    if (tc.channel) bits.push(String(tc.channel));
    if (typeof tc.count === "number") bits.push(`${tc.count}`);
    if (tc.query) bits.push(String(tc.query).slice(0, 80));
    if (tc.url) bits.push(String(tc.url).slice(0, 120));
    if (tc.title) bits.push(`«${String(tc.title).slice(0, 80)}»`);
    if (typeof tc.chars === "number" && tc.chars > 0) bits.push(`${tc.chars} симв.`);
    remember(steps, {
      label: tool,
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
        remember(steps, {
          label: String(st.safe_summary || st.tool_id || st.kind || ""),
          ok: st.status === "ok" || st.status === "succeeded" || st.status === "done",
        });
      }
    }
  }

  return steps.length ? steps : [{ label: humanAction("Думаю над ответом…") }];
}

/** Flatten steps into a short narrative for Claude-style thinking body. */
export function thinkingNarrative(steps: ThinkingStep[], upTo?: number): string {
  const slice = typeof upTo === "number" ? steps.slice(0, Math.max(1, upTo)) : steps;
  return slice
    .map((s) => {
      const label = humanAction(s.label);
      const detail = humanDetail(s.detail);
      return detail ? `${label} — ${detail}` : label;
    })
    .join("\n");
}
