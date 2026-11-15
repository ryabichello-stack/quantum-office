import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  formatRecordTime,
  initialDictate,
  micButtonLabel,
  reduceDictate,
  ruSteps,
  thinkingView,
  thoughtsLabel,
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
    { label: "Читаю запрос" },
    { label: "Смотрю каналы и способ подключения", detail: "telegram" },
    { label: "Готовлю ответ" },
  ];

  it("shows only the current step large and folds the rest", () => {
    const first = thinkingView(steps, { live: true, liveIndex: 1 });
    assert.equal(first.showSummary, false);
    assert.equal(first.current?.label, "Читаю запрос");
    assert.deepEqual(first.summarySteps, []);

    const mid = thinkingView(steps, { live: true, liveIndex: 2 });
    assert.equal(mid.showSummary, true);
    assert.equal(mid.summaryLabel, "Ход мыслей · 1 шаг");
    assert.equal(mid.summarySteps.length, 1);
    assert.equal(mid.current?.label, "Смотрю каналы и способ подключения");

    const last = thinkingView(steps, { live: true, liveIndex: 3 });
    assert.equal(last.summaryLabel, "Ход мыслей · 2 шага");
    assert.equal(last.current?.label, "Готовлю ответ");
  });

  it("collapses the whole trace once the answer is ready", () => {
    const done = thinkingView(steps, { live: false });
    assert.equal(done.current, null);
    assert.equal(done.showSummary, true);
    assert.equal(done.summarySteps.length, 3);
    assert.equal(done.summaryLabel, thoughtsLabel(3));
    assert.equal(done.summaryLabel, "Ход мыслей · 3 шага");
  });

  it("pluralizes the step count", () => {
    assert.equal(ruSteps(1), "1 шаг");
    assert.equal(ruSteps(2), "2 шага");
    assert.equal(ruSteps(5), "5 шагов");
    assert.equal(ruSteps(11), "11 шагов");
    assert.equal(ruSteps(21), "21 шаг");
    assert.equal(thoughtsLabel(11), "Ход мыслей · 11 шагов");
  });
});
