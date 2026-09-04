/**
 * DELNO Crystal Widget — browser STT + speechSynthesis TTS (Commit 3).
 * Public widget has no JWT — uses browser TTS fallback only.
 */
(function (global) {
  "use strict";

  function getSpeechRecognition() {
    return global.SpeechRecognition || global.webkitSpeechRecognition || null;
  }

  function unlockAudioElement(audio) {
    return new Promise(function (resolve) {
      try {
        audio.muted = true;
        audio.src =
          "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAAB9AAACABAAZGF0YQAAAAA=";
        var playPromise = audio.play();
        if (playPromise && playPromise.then) {
          playPromise
            .then(function () {
              audio.pause();
              audio.removeAttribute("src");
              audio.load();
              audio.muted = false;
              resolve();
            })
            .catch(function () {
              audio.muted = false;
              resolve();
            });
        } else {
          audio.muted = false;
          resolve();
        }
      } catch (_) {
        audio.muted = false;
        resolve();
      }
    });
  }

  function speakWithBrowser(text) {
    return new Promise(function (resolve, reject) {
      if (!global.speechSynthesis) {
        reject(new Error("no speech synthesis"));
        return;
      }
      global.speechSynthesis.cancel();
      var utter = new SpeechSynthesisUtterance(text);
      utter.lang = "ru-RU";
      utter.onend = function () {
        resolve();
      };
      utter.onerror = function () {
        reject(new Error("speech synthesis failed"));
      };
      global.speechSynthesis.speak(utter);
    });
  }

  function playReplyTts(text, audio, callbacks) {
    callbacks = callbacks || {};
    if (callbacks.signal && callbacks.signal.aborted) return Promise.resolve(false);

    return speakWithBrowser(text)
      .then(function () {
        callbacks.onStart && callbacks.onStart();
        callbacks.onEnd && callbacks.onEnd();
        return true;
      })
      .catch(function () {
        callbacks.onError && callbacks.onError();
        return false;
      });
  }

  /**
   * @param {object} options
   * @param {(text: string) => Promise<string>} options.onTranscript
   * @param {(userText: string, assistantText: string) => void} [options.onExchange]
   * @param {(phase: string) => void} options.setPhase
   * @param {HTMLAudioElement|null} options.audioEl
   * @param {number} [options.listenSilenceMs]
   */
  function createVoiceController(options) {
    var onTranscript = options.onTranscript;
    var onExchange = options.onExchange;
    var setPhase = options.setPhase;
    var audioEl = options.audioEl || null;
    var listenSilenceMs = options.listenSilenceMs || 8000;

    var engaged = false;
    var recognition = null;
    var heard = false;
    var speaking = false;
    var processing = false;
    var turnId = 0;
    var abortTts = null;
    var errorTimer = null;
    var listenTimer = null;

    function clearErrorTimer() {
      if (errorTimer !== null) {
        clearTimeout(errorTimer);
        errorTimer = null;
      }
    }

    function clearListenTimer() {
      if (listenTimer !== null) {
        clearTimeout(listenTimer);
        listenTimer = null;
      }
    }

    function resetListenTimer() {
      clearListenTimer();
      listenTimer = setTimeout(function () {
        if (engaged && !processing && !speaking) stop();
      }, listenSilenceMs);
    }

    function stop() {
      turnId += 1;
      clearListenTimer();
      if (recognition) {
        try {
          recognition.abort();
        } catch (_) {}
      }
      recognition = null;
      if (abortTts) abortTts.abort();
      abortTts = null;
      processing = false;
      speaking = false;
      heard = false;
      engaged = false;
      clearErrorTimer();
      if (audioEl) {
        audioEl.pause();
        audioEl.removeAttribute("src");
      }
      if (global.speechSynthesis) global.speechSynthesis.cancel();
      setPhase("idle");
    }

    function showError(userText, assistantText) {
      clearErrorTimer();
      setPhase("error");
      if (onExchange) onExchange(userText, assistantText);
      errorTimer = setTimeout(function () {
        stop();
      }, 3000);
    }

    function answer(text, fromMic) {
      var id = ++turnId;
      processing = true;
      clearListenTimer();
      if (recognition) {
        try {
          recognition.abort();
        } catch (_) {}
      }
      recognition = null;
      setPhase("think");

      return onTranscript(text)
        .then(function (reply) {
          if (id !== turnId) return;
          if (!reply || !String(reply).trim()) {
            processing = false;
            showError(text, "Не удалось получить ответ.");
            return;
          }
          processing = false;
          if (onExchange) onExchange(text, reply);
          speaking = true;
          abortTts = new AbortController();

          if (!audioEl) {
            speaking = false;
            if (engaged) {
              setPhase("listen");
              startMic();
            } else {
              stop();
            }
            return;
          }

          var startTts = function () {
            return playReplyTts(reply, audioEl, {
              onStart: function () {
                if (id === turnId) setPhase("speak");
              },
              onEnd: function () {
                speaking = false;
                if (engaged) {
                  setPhase("listen");
                  startMic();
                } else {
                  stop();
                }
              },
              onError: function () {
                speaking = false;
                if (engaged) {
                  setPhase("listen");
                  startMic();
                } else {
                  stop();
                }
              },
              signal: abortTts.signal,
            });
          };

          if (fromMic) {
            return new Promise(function (r) {
              setTimeout(r, 80);
            }).then(startTts);
          }
          return startTts();
        })
        .catch(function () {
          processing = false;
          if (id !== turnId) return;
          showError(text, "Сейчас не удалось получить ответ. Попробуйте ещё раз.");
        });
    }

    function startMic() {
      if (!engaged || processing || speaking) return;
      var SpeechRecognition = getSpeechRecognition();
      if (!SpeechRecognition) {
        showError("Голос", "Браузер не поддерживает распознавание речи. Напишите вопрос в чате.");
        return;
      }

      heard = false;
      setPhase("listen");
      resetListenTimer();
      if (recognition) {
        try {
          recognition.abort();
        } catch (_) {}
      }
      recognition = new SpeechRecognition();
      recognition.lang = "ru-RU";
      recognition.interimResults = true;
      recognition.continuous = true;

      var pending = "";
      recognition.onresult = function (event) {
        if (!engaged || processing || speaking) return;
        heard = true;
        resetListenTimer();
        for (var i = event.resultIndex; i < event.results.length; i += 1) {
          if (event.results[i].isFinal) {
            pending = (pending + " " + event.results[i][0].transcript).trim();
          }
        }
      };

      recognition.onerror = function () {
        recognition = null;
      };

      recognition.onend = function () {
        recognition = null;
        if (pending && engaged && !processing && !speaking) {
          var captured = pending;
          pending = "";
          answer(captured, true);
        }
      };

      try {
        recognition.start();
      } catch (_) {
        /* ignore */
      }
    }

    function toggle() {
      if (engaged) {
        stop();
        return;
      }
      engaged = true;
      if (audioEl) unlockAudioElement(audioEl);
      startMic();
    }

    return {
      toggle: toggle,
      stop: stop,
      isActive: function () {
        return engaged;
      },
    };
  }

  global.createDelnoVoiceController = createVoiceController;
})(typeof window !== "undefined" ? window : globalThis);
