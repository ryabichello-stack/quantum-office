import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  formatRecordTime,
  initialDictate,
  micButtonLabel,
  reduceDictate,
  doneActionsLabel,
  humanAction,
  reduceLiveTrace,
  ruActions,
  thinkingView,
  type LiveTrace,
  waveHeights,
  type DictateSnapshot,
} from "./hermesUiStates";
import { sttErrorMessage } from "./sttErrors";

function phase(state: DictateSnapshot) {
  return state.phase;
}

describe("microphone states", () => {
  it("goes recording → recognizing → draft, and does not auto-send", () => {
    let state = reduceDictate(initialDictate(), { type: "start" });
    assert.equal(phase(state), "recording");
    assert.equal(state.error, "");
    assert.equal(micButtonLabel(state.phase), "Остановить запись");

    state = reduceDictate(state, { type: "tick", elapsedMs: 4200 });
    state = reduceDictate(state, { type: "level", level: 0.8 });
    assert.equal(formatRecordTime(state.elapsedMs), "0:04");
    assert.equal(state.level, 0.8);
    assert.equal(state.streaming, false);

    state = reduceDictate(state, { type: "stop" });
    assert.equal(phase(state), "transcribing");
    assert.equal(micButtonLabel(state.phase), "Распознаю речь");
    assert.equal(state.level, 0);

    state = reduceDictate(state, { type: "recognized", text: "добрый день" });
    assert.equal(phase(state), "idle");
    assert.equal(state.draft, "добрый день");
    assert.equal(state.error, "");
  });

  it("shows streaming partials only when a streaming engine emits them", () => {
    let state = reduceDictate(initialDictate(), { type: "start" });
    assert.equal(state.streaming, false);
    state = reduceDictate(state, { type: "partial", text: "привет" });
    assert.equal(state.streaming, true);
    assert.equal(state.draft, "привет");
    state = reduceDictate(state, { type: "stop" });
    assert.equal(state.streaming, true);
    assert.equal(state.draft, "привет");
  });

  it("ignores ticks, levels and partials outside of recording", () => {
    const idle = initialDictate();
    assert.equal(reduceDictate(idle, { type: "tick", elapsedMs: 1000 }).elapsedMs, 0);
    assert.equal(reduceDictate(idle, { type: "stop" }).phase, "idle");
    const recognizing = reduceDictate(reduceDictate(idle, { type: "start" }), { type: "stop" });
    assert.equal(reduceDictate(recognizing, { type: "partial", text: "нет" }).draft, "");
    assert.equal(reduceDictate(recognizing, { type: "level", level: 1 }).level, 0);
  });

  it("maps failures to Russian copy and never surfaces STT_FAILED", () => {
    const recording = reduceDictate(initialDictate(), { type: "start" });
    const failed = reduceDictate(recording, {
      type: "fail",
      message: sttErrorMessage("STT_FAILED"),
    });
    assert.equal(failed.phase, "idle");
    assert.equal(failed.error, "Не удалось распознать речь. Попробуйте ещё раз.");
    assert.equal(failed.error.includes("STT_FAILED"), false);

    const denied = sttErrorMessage("not-allowed");
    assert.match(denied, /микрофон/i);
    assert.equal(denied.includes("not-allowed"), false);

    const unknown = sttErrorMessage("INTERNAL_BOMB");
    assert.equal(unknown.includes("INTERNAL_BOMB"), false);
    assert.match(unknown, /распознать/i);

    assert.match(sttErrorMessage("STT_EMPTY"), /Стоп/);
    assert.match(sttErrorMessage("STT_NOT_CONFIGURED"), /текстом/);
  });

  it("clamps the level and keeps silence bars shorter than speech", () => {
    const recording = reduceDictate(initialDictate(), { type: "start" });
    const clipped = reduceDictate(recording, { type: "level", level: 4 });
    assert.equal(clipped.level, 1);
    const quiet = waveHeights(0, 1000);
    const loud = waveHeights(1, 1000);
    assert.equal(quiet.length, 5);
    assert.ok(Math.max(...loud) > Math.max(...quiet));
    assert.ok(quiet.every((h) => h <= 6));
  });
});

describe("Hermes thinking block", () => {
  const steps = [
    { label: "Читаю запрос…" },
    { label: "web.research", detail: "https://dlno.ru · diy_web_research" },
    { label: "phones.provision" },
    { label: "Думаю над ответом…" },
  ];

  it("shows the current action in the collapsed line and keeps the same words in the list", () => {
    const first = thinkingView(steps, { live: true, liveIndex: 1 });
    assert.equal(first.line, "Читаю запрос…");
    assert.equal(first.steps.length, 1);

    const mid = thinkingView(steps, { live: true, liveIndex: 2 });
    assert.equal(mid.line, "Ищу на сайте компании…");
    assert.equal(mid.line.includes("web.research"), false);
    assert.equal(mid.steps.length, 2);
    assert.equal(mid.steps[1].label, "Ищу на сайте компании…");
    assert.equal(mid.steps[1].detail, "https://dlno.ru");
    assert.equal(JSON.stringify(mid).includes("diy_web_research"), false);

    const last = thinkingView(steps, { live: true, liveIndex: 4 });
    assert.equal(last.line, "Думаю над ответом…");
    assert.equal(last.steps[2].label, "Привязываю номер…");
  });

  it("collapses to a short count once the answer is ready", () => {
    const done = thinkingView(steps, { live: false });
    assert.equal(done.line, "Сделал 4 действия");
    assert.equal(done.line.includes("Ход мыслей"), false);
    assert.equal(done.steps.length, 4);
    assert.equal(done.steps.every((step) => !step.label.includes(".")), true);
  });

  it("names tools in plain language and hides unknown ids", () => {
    assert.equal(humanAction("credentials.open_form"), "Открываю безопасную форму…");
    assert.equal(humanAction("web.search"), "Ищу в интернете…");
    assert.equal(humanAction("web.fetch"), "Читаю страницу…");
    assert.equal(humanAction("get_knowledge"), "Проверяю базу знаний…");
    assert.equal(humanAction("telephony.script_save"), "Сохраняю сценарий звонков…");
    assert.equal(humanAction("suggest_calendar_slots"), "Смотрю свободное время…");
    assert.equal(humanAction("send_mail_draft"), "Готовлю письмо…");
    assert.equal(humanAction("Инструмент: phones.list"), "Смотрю номера…");
    const unknown = humanAction("mystery.tool_x");
    assert.equal(unknown, "Выполняю действие…");
    assert.equal(unknown.includes("mystery"), false);
  });

  it("follows live Hermes tool events and thinks between them", () => {
    let trace: LiveTrace = { steps: [], awaiting: true, seen: [] };
    assert.equal(thinkingView(trace.steps, { live: true, awaiting: trace.awaiting }).line, "Думаю над ответом…");
    trace = reduceLiveTrace(trace, { phase: "tool", tool: "web.research", tool_call_id: "c1" });
    assert.equal(trace.awaiting, false);
    assert.equal(thinkingView(trace.steps, { live: true, awaiting: false }).line, "Ищу на сайте компании…");
    trace = reduceLiveTrace(trace, { phase: "tool", tool: "web.research", tool_call_id: "c1" });
    assert.equal(trace.steps.length, 1);
    trace = reduceLiveTrace(trace, { phase: "between" });
    assert.equal(thinkingView(trace.steps, { live: true, awaiting: true }).line, "Думаю над ответом…");
    assert.equal(thinkingView(trace.steps, { live: true, awaiting: true }).steps.length, 1);
    trace = reduceLiveTrace(trace, { phase: "tool", tool: "phones.provision", tool_call_id: "c2" });
    const done = thinkingView(trace.steps, { live: false });
    assert.equal(done.line, "Сделал 2 действия");
    assert.equal(done.steps.map((s) => s.label).join("|").includes("phones"), false);
  });

  it("pluralizes the finished summary", () => {
    assert.equal(ruActions(1), "1 действие");
    assert.equal(ruActions(2), "2 действия");
    assert.equal(ruActions(4), "4 действия");
    assert.equal(ruActions(5), "5 действий");
    assert.equal(ruActions(11), "11 действий");
    assert.equal(ruActions(21), "21 действие");
    assert.equal(doneActionsLabel(4), "Сделал 4 действия");
  });
});
