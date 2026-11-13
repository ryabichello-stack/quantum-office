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

  globalThis.fetch = mock.fn(async () => ({
    ok: true,
    blob: async () => new Blob(["audio"], { type: "audio/mpeg" }),
  }));

  globalThis.URL.createObjectURL = () => "blob:test";
  globalThis.URL.revokeObjectURL = () => {};
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
      pause: () => {},
      removeAttribute: () => {},
    };

    class SpeechRecognitionMock {
      lang = "ru-RU";
      interimResults = false;
      continuous = false;
      onstart = null;
      onresult = null;
      onerror = null;
      onend = null;
      start() {
        queueMicrotask(() => this.onstart?.());
      }
      stop() {
        queueMicrotask(() => this.onend?.());
      }
    }

    globalThis.window.SpeechRecognition = SpeechRecognitionMock;
  });

  afterEach(() => {
    mock.reset();
  });

  function makeController(listenSilenceMs = 200) {
    const onTranscript = mock.fn(async (text) => `reply:${text}`);
    const controller = createVoiceController({
      onTranscript,
      setPhase: (phase) => phases.push(phase),
      audioRef: { current: audioEl },
      listenSilenceMs,
    });
    return { controller, onTranscript };
  }

  it("askText goes think → speak → listen and stops after silence timeout", async () => {
    const { controller } = makeController(200);
    const done = controller.askText("Что умеет DELNO?");
    await new Promise((r) => setTimeout(r, 50));
    assert.ok(phases.includes("think"));
    assert.ok(phases.includes("speak"));
    await new Promise((r) => setTimeout(r, 30));
    assert.ok(phases.includes("listen"), `expected listen, got ${phases.join(" → ")}`);
    await new Promise((r) => setTimeout(r, 280));
    assert.equal(phases.at(-1), "idle", `expected idle after silence, got ${phases.join(" → ")}`);
    await done;
  });

  it("toggle stop is immediate while listening", async () => {
    const { controller } = makeController(5000);
    controller.toggle();
    await new Promise((r) => setTimeout(r, 20));
    assert.equal(phases.at(-1), "listen");
    controller.toggle();
    assert.equal(phases.at(-1), "idle");
  });

  it("starting one controller stops another via mutex", async () => {
    const phasesA = [];
    const phasesB = [];
    const a = createVoiceController({
      onTranscript: async () => "a",
      setPhase: (p) => phasesA.push(p),
      audioRef: { current: audioEl },
      listenSilenceMs: 5000,
    });
    const b = createVoiceController({
      onTranscript: async () => "b",
      setPhase: (p) => phasesB.push(p),
      audioRef: { current: audioEl },
      listenSilenceMs: 5000,
    });
    a.toggle();
    await new Promise((r) => setTimeout(r, 20));
    b.toggle();
    assert.equal(phasesA.at(-1), "idle");
    assert.equal(phasesB.at(-1), "listen");
  });
});
