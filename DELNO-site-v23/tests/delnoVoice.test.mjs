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
    if (String(url).includes("/voice/realtime")) {
      return {
        ok: true,
        text: async () => "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\n",
      };
    }
    return {
      ok: true,
      blob: async () => new Blob(["audio"], { type: "audio/mpeg" }),
    };
  });

  globalThis.URL.createObjectURL = () => "blob:test";
  globalThis.URL.revokeObjectURL = () => {};

  class DataChannelMock {
    onmessage = null;
    close() {}
    send() {}
  }

  class RTCPeerConnectionMock {
    ontrack = null;
    localDescription = { sdp: "offer-sdp" };
    constructor() {
      this._channel = new DataChannelMock();
    }
    createDataChannel() {
      return this._channel;
    }
    addTrack() {}
    async createOffer() {
      return { type: "offer", sdp: "offer-sdp" };
    }
    async setLocalDescription() {}
    async setRemoteDescription() {
      queueMicrotask(() => {
        this.ontrack?.({ streams: [{ id: "remote" }] });
        this._channel.onmessage?.({
          data: JSON.stringify({ type: "session.created" }),
        });
      });
    }
    close() {}
  }

  globalThis.RTCPeerConnection = RTCPeerConnectionMock;

  globalThis.navigator = {
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

  it("toggle starts Realtime listen and stops on second toggle", async () => {
    const { controller } = makeController();
    controller.toggle();
    await new Promise((r) => setTimeout(r, 30));
    assert.ok(phases.includes("listen"));
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
    });
    const b = createVoiceController({
      onTranscript: async () => "b",
      setPhase: (p) => phasesB.push(p),
      audioRef: { current: audioEl },
    });
    a.toggle();
    await new Promise((r) => setTimeout(r, 30));
    b.toggle();
    assert.equal(phasesA.at(-1), "idle");
    assert.ok(phasesB.includes("listen"));
  });
});
