import assert from "node:assert/strict";
import { describe, it, mock, beforeEach, afterEach } from "node:test";
import { createVoiceController } from "../lib/delnoVoice.ts";

function installDomStubs() {
  globalThis.window = {
    speechSynthesis: { cancel: () => {} },
  };

  globalThis.setTimeout = globalThis.setTimeout;
  globalThis.clearTimeout = globalThis.clearTimeout;

  globalThis.Audio = class {
    muted = false;
    src = "";
    autoplay = false;
    playsInline = false;
    srcObject = null;
    onplaying = null;
    onended = null;
    onerror = null;
    pause() {}
    removeAttribute() {}
    play() {
      queueMicrotask(() => this.onplaying?.());
      queueMicrotask(() => this.onended?.());
      return Promise.resolve();
    }
  };

  globalThis.fetch = mock.fn(async (url) => {
    if (String(url).includes("/api/tts")) {
      return {
        ok: true,
        blob: async () => new Blob(["audio"], { type: "audio/mpeg" }),
      };
    }
    return {
      ok: true,
      blob: async () => new Blob(["audio"], { type: "audio/mpeg" }),
    };
  });

  globalThis.URL.createObjectURL = () => "blob:test";
  globalThis.URL.revokeObjectURL = () => {};

  globalThis.navigator = {
    maxTouchPoints: 0,
    userAgent: "Desktop",
    mediaDevices: {
      getUserMedia: async () => ({
        getTracks: () => [{ stop: () => {} }],
      }),
    },
  };
}

describe("createVoiceController", () => {
  let phases = [];
  let audioEl;

  beforeEach(() => {
    phases = [];
    installDomStubs();
    audioEl = {
      muted: false,
      src: "",
      autoplay: false,
      playsInline: false,
      srcObject: null,
      pause: () => {},
      removeAttribute: () => {},
      play: () => Promise.resolve(),
    };
  });

  afterEach(() => {
    mock.reset();
  });

  function makeController() {
    const onTranscript = mock.fn(async (text) => `reply:${text}`);
    const controller = createVoiceController({
      onTranscript,
      setPhase: (phase) => phases.push(phase),
      audioRef: { current: audioEl },
    });
    return { controller, onTranscript };
  }

  it("askText goes think → speak → idle", async () => {
    const { controller } = makeController();
    await controller.askText("Что умеет DELNO?");
    assert.ok(phases.includes("think"));
    assert.ok(phases.includes("speak"));
    assert.equal(phases.at(-1), "idle");
  });

  it("askText calls onTranscript with user message", async () => {
    const { controller, onTranscript } = makeController();
    await controller.askText("Сколько стоит?");
    assert.equal(onTranscript.mock.calls.length, 1);
    assert.equal(onTranscript.mock.calls[0].arguments[0], "Сколько стоит?");
  });

  it("starting one controller stops another via mutex", async () => {
    const phasesA = [];
    const phasesB = [];
    const a = createVoiceController({
      onTranscript: async () => "a",
      setPhase: (p) => phasesA.push(p),
      audioRef: { current: audioEl },
    });
    const b = createVoiceController({
      onTranscript: async () => "b",
      setPhase: (p) => phasesB.push(p),
      audioRef: { current: audioEl },
    });
    await a.askText("test a");
    await b.askText("test b");
    assert.equal(phasesA.at(-1), "idle");
    assert.ok(phasesB.includes("think"));
  });
});
