/**
 * DELNO Crystal Widget — text chat + unified voice session (Commit 3).
 * Uses DelnoWidgetClient → /v1/public/widget/* (never operator/chat).
 */
(function (global) {
  "use strict";

  function delay(ms) {
    return new Promise(function (r) {
      setTimeout(r, ms);
    });
  }

  function isLikelyName(text) {
    var s = String(text || "").trim();
    if (!s || s.length > 48) return false;
    if (/[?!.:,;]/.test(s)) return false;
    return s.split(/\s+/).length <= 4;
  }

  function isLikelyPhone(text) {
    var digits = String(text || "").replace(/\D/g, "");
    return digits.length >= 10 && digits.length <= 11;
  }

  function personalizedGreeting(name) {
    var first = String(name || "")
      .trim()
      .split(/\s+/)[0];
    return first
      ? "Приятно познакомиться, " + first + ". Что ещё хотите уточнить?"
      : "Приятно познакомиться. Что ещё хотите уточнить?";
  }

  function visitorPayload(state) {
    return {
      name: state.name || null,
      phone: null,
      page_url: typeof location !== "undefined" ? location.href : null,
      referrer: typeof document !== "undefined" ? document.referrer || null : null,
    };
  }

  function initDelnoWidgetChat(options) {
    var form = options.form;
    var input = options.input;
    var body = options.body;
    var send = options.sendBtn;
    var panel = options.panel;
    var textToggle = options.textToggle;
    var client = options.client;
    var mount = options.mount;
    var audioEl = options.audioEl;

    if (!form || !input || !body || !send) return;

    var state = {
      name: localStorage.getItem("delno_widget_name") || "",
      askedName: localStorage.getItem("delno_widget_asked_name") === "1",
      awaitingName: false,
      awaitingPhone: false,
      busy: false,
    };

    var voiceController = null;

    function setVoicePhase(phase) {
      if (!mount) return;
      var active = phase !== "idle";
      if (active) mount.setAttribute("data-voice-active", "true");
      else mount.removeAttribute("data-voice-active");
      if (phase === "idle") mount.removeAttribute("data-voice-phase");
      else mount.setAttribute("data-voice-phase", phase);
    }

    function openPanel() {
      if (textToggle) textToggle.checked = true;
      if (panel) panel.classList.add("is-open");
      setTimeout(function () {
        input.focus({ preventScroll: true });
      }, 180);
    }

    function autoSize() {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 104) + "px";
    }

    function scrollDown() {
      requestAnimationFrame(function () {
        body.scrollTop = body.scrollHeight;
      });
    }

    function appendMessage(role, text, extraClass) {
      var row = document.createElement("div");
      row.className = "message-row " + role;
      var msg = document.createElement("div");
      msg.className = "message" + (extraClass ? " " + extraClass : "");
      msg.textContent = text;
      row.appendChild(msg);
      body.appendChild(row);
      scrollDown();
      return row;
    }

    function appendTyping() {
      var row = document.createElement("div");
      row.className = "message-row assistant";
      row.dataset.typing = "1";
      var msg = document.createElement("div");
      msg.className = "message typing";
      msg.innerHTML = "<i></i><i></i><i></i>";
      row.appendChild(msg);
      body.appendChild(row);
      scrollDown();
      return row;
    }

    function appendExchange(userText, assistantText) {
      appendMessage("user", userText);
      appendMessage("assistant", assistantText);
    }

    function setBusy(v) {
      state.busy = v;
      send.disabled = v || !input.value.trim();
      input.disabled = v;
      if (!v) input.focus({ preventScroll: true });
    }

    function backendErrorMessage() {
      return "Сейчас не могу ответить. Попробуйте ещё раз или напишите позже.";
    }

    async function backendReply(message, modality) {
      if (!client) return null;
      await client.ensureSession();
      return client.sendMessage(message, visitorPayload(state), { modality: modality || "text" });
    }

    async function sendVoiceQuery(text) {
      var value = String(text || "").trim();
      if (!value) return "Не удалось распознать вопрос. Попробуйте ещё раз.";

      if (state.awaitingName && isLikelyName(value)) {
        state.name = value;
        state.awaitingName = false;
        localStorage.setItem("delno_widget_name", state.name);
        if (client) await client.syncVisitor({ name: state.name }).catch(function () {});
        return personalizedGreeting(state.name);
      }

      if (state.awaitingPhone && isLikelyPhone(value)) {
        state.awaitingPhone = false;
        if (client) await client.syncVisitor({ phone: value }).catch(function () {});
        return "Спасибо! Передал контакт — при необходимости с вами свяжутся.";
      }

      var payload = null;
      try {
        payload = await backendReply(value, "voice");
      } catch (err) {
        console.warn("DELNO widget voice:", err);
      }

      var answer = payload && payload.message ? payload.message : backendErrorMessage();

      var backendRequestsName = payload && payload.next_step === "ask_name";
      var backendRequestsPhone = payload && payload.next_step === "ask_phone";

      if (!state.name && (!state.askedName || backendRequestsName) && value.length >= 8) {
        state.awaitingName = true;
        state.askedName = true;
        localStorage.setItem("delno_widget_asked_name", "1");
        return answer + " Кстати, как я могу к вам обращаться?";
      }
      if (
        state.name &&
        backendRequestsPhone &&
        !localStorage.getItem("delno_widget_lead_id")
      ) {
        state.awaitingPhone = true;
        return answer + " Оставьте номер телефона — передам коллеге, если понадобится связаться.";
      }

      return answer;
    }

    async function sendMessage(text) {
      var value = String(text || "").trim();
      if (!value || state.busy) return;

      appendMessage("user", value);
      input.value = "";
      autoSize();
      setBusy(true);

      if (state.awaitingName && isLikelyName(value)) {
        var typingName = appendTyping();
        await delay(320);
        typingName.remove();
        state.name = value;
        state.awaitingName = false;
        localStorage.setItem("delno_widget_name", state.name);
        if (client) await client.syncVisitor({ name: state.name }).catch(function () {});
        appendMessage("assistant", personalizedGreeting(state.name));
        setBusy(false);
        return;
      }

      if (state.awaitingPhone && isLikelyPhone(value)) {
        var typingPhone = appendTyping();
        await delay(320);
        typingPhone.remove();
        state.awaitingPhone = false;
        if (client) await client.syncVisitor({ phone: value }).catch(function () {});
        appendMessage("assistant", "Спасибо! Передал контакт — при необходимости с вами свяжутся.");
        setBusy(false);
        return;
      }

      var typing = appendTyping();
      var payload = null;
      try {
        payload = await backendReply(value, "text");
      } catch (err) {
        console.warn("DELNO widget:", err);
      }

      await delay(payload ? 120 : 400);
      typing.remove();

      var answer = payload && payload.message ? payload.message : backendErrorMessage();
      appendMessage("assistant", answer);

      var backendRequestsName = payload && payload.next_step === "ask_name";
      var backendRequestsPhone = payload && payload.next_step === "ask_phone";

      if (!state.name && (!state.askedName || backendRequestsName) && value.length >= 8) {
        await delay(260);
        appendMessage("assistant", "Кстати, как я могу к вам обращаться?");
        state.awaitingName = true;
        state.askedName = true;
        localStorage.setItem("delno_widget_asked_name", "1");
      } else if (
        state.name &&
        backendRequestsPhone &&
        !localStorage.getItem("delno_widget_lead_id")
      ) {
        await delay(260);
        appendMessage("assistant", "Оставьте номер телефона — передам коллеге, если понадобится связаться.");
        state.awaitingPhone = true;
      }

      setBusy(false);
    }

    async function loadHistory() {
      if (!client) return;
      try {
        await client.ensureSession();
        var payload = await client.fetchHistory();
        var messages = (payload && payload.messages) || [];
        if (!messages.length) return;
        body.innerHTML = "";
        for (var i = 0; i < messages.length; i += 1) {
          var item = messages[i];
          if (item.role === "user" || item.role === "assistant") {
            appendMessage(item.role, item.text);
          }
        }
      } catch (err) {
        console.warn("DELNO widget history:", err);
      }
    }

    input.addEventListener("input", function () {
      autoSize();
      send.disabled = state.busy || !input.value.trim();
    });

    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form.requestSubmit();
      }
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      sendMessage(input.value);
    });

    if (textToggle) {
      textToggle.addEventListener("change", function () {
        if (textToggle.checked) {
          setTimeout(function () {
            input.focus({ preventScroll: true });
          }, 180);
        }
      });
    }

    if (options.chatButton) {
      options.chatButton.addEventListener("click", function (e) {
        e.preventDefault();
        openPanel();
      });
    }

    if (options.orbButton && typeof createDelnoVoiceController === "function") {
      voiceController = createDelnoVoiceController({
        onTranscript: sendVoiceQuery,
        onExchange: appendExchange,
        setPhase: setVoicePhase,
        audioEl: audioEl || null,
        buildTtsUrl: client
          ? function (text) {
              return client.buildTtsUrl(text);
            }
          : null,
        onFallbackToText: function (message) {
          openPanel();
          appendMessage("assistant", message);
        },
      });
      options.orbButton.addEventListener("click", function (e) {
        e.preventDefault();
        voiceController.toggle();
      });
    } else if (options.orbButton) {
      options.orbButton.addEventListener("click", function (e) {
        e.preventDefault();
        openPanel();
        appendMessage(
          "assistant",
          "Голосовой режим недоступен в этом браузере. Напишите ваш вопрос здесь.",
        );
      });
    }

    autoSize();
    send.disabled = true;

    if (client) {
      client.ensureSession().then(loadHistory).catch(function () {});
    }

    return {
      sendMessage: sendMessage,
      sendVoiceQuery: sendVoiceQuery,
      appendExchange: appendExchange,
      openPanel: openPanel,
      stopVoice: function () {
        if (voiceController) voiceController.stop();
      },
    };
  }

  global.initDelnoWidgetChat = initDelnoWidgetChat;
})(typeof window !== "undefined" ? window : globalThis);
