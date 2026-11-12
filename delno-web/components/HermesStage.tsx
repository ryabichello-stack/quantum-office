"use client";

import {
  FormEvent,
  PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  AlertTriangle,
  ArrowUp,
  Camera,
  CheckCircle2,
  Mic,
  PanelRight,
  Paperclip,
  Sparkles,
  X,
} from "lucide-react";
import { CrystalOrb } from "@/components/CrystalOrb";
import { ConfirmCard } from "@/components/ConfirmCard";
import { CredentialFormCard, type CredentialFormSpec } from "@/components/CredentialFormCard";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  apiConversations,
  apiConversationMessages,
  apiOperatorChat,
  apiOperatorConfirm,
  apiTenantSecretSave,
  type CredentialFormSpec as ApiCredentialFormSpec,
  type KnowledgeSource,
  type PendingConfirmation,
  type SuggestedAction,
} from "@/lib/api";
import {
  apiBillingEnsure,
  apiBillingSummary,
  apiCallsList,
  apiChannelQrStart,
  apiAgentTasks,
  apiHermesHealth,
  apiHermesNousStatus,
  apiHermesSetup,
  apiOfficeLoop,
  type AgentTaskItem,
  type BillingSummary,
  type CallSessionItem,
  type HermesHealthStatus,
  type HermesNousStatus,
  type HermesSetupStatus,
  type OfficeLoopStatus,
} from "@/lib/hermesApi";
import {
  canAddMore,
  fileToOperatorAttachment,
  makePendingAttachment,
  type PendingHermesAttachment,
} from "@/lib/hermesAttachments";
import { cn } from "@/lib/utils";
import { useDictateToInput } from "@/lib/useDictateToInput";
import { useOperatorVoice } from "@/lib/useOperatorVoice";

type PendingDownload = {
  filename: string;
  title: string;
  body: string;
  content_type?: string;
};

type ChatLine = {
  role: "user" | "assistant";
  text: string;
  sources?: KnowledgeSource[];
  pending?: PendingConfirmation | null;
  credentialForm?: CredentialFormSpec | null;
  download?: PendingDownload | null;
  suggestions?: SuggestedAction[];
  previews?: { url: string; name: string }[];
};

function triggerMarkdownDownload(file: PendingDownload) {
  const blob = new Blob([file.body], { type: file.content_type || "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = file.filename || "template.md";
  a.click();
  URL.revokeObjectURL(url);
}

const QUICK_PROMPTS = [
  { title: "О компании", text: "Я владелец офиса. Покажи статус сетапа и скажи, что сделать следующим шагом." },
  { title: "Сайт → знания", text: "Зайди на мой сайт и собери знания в базу" },
  { title: "Телефон", text: "Настрой телефон секретаря" },
  { title: "SIP Mango", text: "Открой безопасную форму SIP-пароля Mango" },
  { title: "Сетап", text: "Что ещё настроить в офисе?" },
  { title: "Здоровье", text: "Проверь здоровье офиса" },
  { title: "Звонки", text: "Какие звонки были сегодня?" },
  { title: "Затраты", text: "Покажи расход токенов и баланс" },
];

function useCompactHermes(breakpoint = 720) {
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpoint}px)`);
    const sync = () => setCompact(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, [breakpoint]);
  return compact;
}

function HermesAvatar({ className }: { className?: string }) {
  return (
    <Avatar size="sm" className={cn("hx-msg-avatar rounded-[11px] bg-[var(--y)] text-black after:border-black/10", className)}>
      <AvatarFallback className="rounded-[11px] bg-[var(--y)] text-black">
        <Sparkles size={14} />
      </AvatarFallback>
    </Avatar>
  );
}

export function HermesStage({ token }: { token: string }) {
  const compact = useCompactHermes();
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [message, setMessage] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const [activePending, setActivePending] = useState<PendingConfirmation | null>(null);
  const [activeSecretForm, setActiveSecretForm] = useState<CredentialFormSpec | null>(null);
  const [secretBusy, setSecretBusy] = useState(false);
  const [setup, setSetup] = useState<HermesSetupStatus | null>(null);
  const [health, setHealth] = useState<HermesHealthStatus | null>(null);
  const [calls, setCalls] = useState<CallSessionItem[]>([]);
  const [billing, setBilling] = useState<BillingSummary | null>(null);
  const [officeLoop, setOfficeLoop] = useState<OfficeLoopStatus | null>(null);
  const [nousStatus, setNousStatus] = useState<HermesNousStatus | null>(null);
  const [agentTasks, setAgentTasks] = useState<AgentTaskItem[]>([]);
  const [bootstrapped, setBootstrapped] = useState(false);
  const [qrBusy, setQrBusy] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<PendingHermesAttachment[]>([]);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const mountRef = useRef<HTMLDivElement>(null);
  const threadEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messageRef = useRef(message);
  messageRef.current = message;
  const pendingRef = useRef(pendingFiles);
  pendingRef.current = pendingFiles;

  const refreshPanels = useCallback(async () => {
    try {
      const [s, h, c, b, loop, nous, tasks] = await Promise.all([
        apiHermesSetup(token).catch(() => null),
        apiHermesHealth(token).catch(() => null),
        apiCallsList(token, 8).catch(() => ({ ok: true, items: [] as CallSessionItem[] })),
        apiBillingEnsure(token)
          .catch(() => apiBillingSummary(token))
          .catch(() => null),
        apiOfficeLoop(token).catch(() => null),
        apiHermesNousStatus(token).catch(() => null),
        apiAgentTasks(token, 8).catch(() => ({ ok: true, items: [] as AgentTaskItem[] })),
      ]);
      if (s) setSetup(s);
      if (h) setHealth(h);
      setCalls(c?.items || []);
      if (b) setBilling(b);
      if (loop) setOfficeLoop(loop);
      if (nous) setNousStatus(nous);
      setAgentTasks(tasks?.items || []);
    } catch {
      /* panels are best-effort; chat still works */
    }
  }, [token]);

  async function startQr(channelType: string) {
    if (qrBusy) return;
    setQrBusy(true);
    try {
      const out = await apiChannelQrStart(token, channelType);
      setLines((prev) => [
        ...prev,
        { role: "assistant", text: out.message_ru || `QR-сессия ${channelType}: ${out.account_id}` },
      ]);
    } catch {
      setError("Не удалось стартовать QR-подключение канала.");
    } finally {
      setQrBusy(false);
    }
  }

  useEffect(() => {
    void refreshPanels();
  }, [refreshPanels]);

  const clearPending = useCallback((items: PendingHermesAttachment[]) => {
    for (const item of items) {
      if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
    }
  }, []);

  const addFiles = useCallback((files: FileList | File[]) => {
    const list = Array.from(files);
    if (!list.length) return;
    setError("");
    setPendingFiles((prev) => {
      const next = [...prev];
      for (const file of list) {
        if (!canAddMore(next.length)) {
          setError("Максимум 4 вложения за раз");
          break;
        }
        const made = makePendingAttachment(file);
        if ("error" in made) {
          setError(made.error);
          continue;
        }
        next.push(made);
      }
      return next;
    });
  }, []);

  const removePending = useCallback((id: string) => {
    setPendingFiles((prev) => {
      const target = prev.find((p) => p.id === id);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((p) => p.id !== id);
    });
  }, []);

  const sendText = useCallback(
    async (text: string, modality: "text" | "voice" = "text", withPending = false) => {
      const question = text.trim();
      const attachSource = withPending ? pendingRef.current : [];
      if ((!question && attachSource.length === 0) || sending) return null;
      setSending(true);
      setError("");
      setActivePending(null);
      const previews = attachSource
        .filter((a) => a.previewUrl)
        .map((a) => ({ url: a.previewUrl!, name: a.filename }));
      const label =
        question ||
        (attachSource.length
          ? attachSource.map((a) => (a.kind === "image" ? `🖼 ${a.filename}` : `📎 ${a.filename}`)).join(" ")
          : "");
      if (modality === "text") {
        setLines((prev) => [...prev, { role: "user", text: label, previews }]);
      }
      try {
        const attachments = await Promise.all(attachSource.map((a) => fileToOperatorAttachment(a.file)));
        if (withPending) {
          clearPending(attachSource);
          setPendingFiles([]);
        }
        const result = await apiOperatorChat(
          token,
          question,
          conversationId || undefined,
          modality,
          "hermes",
          attachments,
        );
        setConversationId(result.conversation_id);
        const pending = result.pending_confirmation || null;
        if (pending) setActivePending(pending);
        const secretForm = (result.pending_credential_form || null) as ApiCredentialFormSpec | null;
        if (secretForm) setActiveSecretForm(secretForm);
        const download = (result.pending_download || null) as PendingDownload | null;
        const suggestions = (result.suggested_actions || []).filter(
          (a) => a?.title && a?.text,
        );
        const redactUser = Boolean(secretForm);
        const safeUserLabel = redactUser
          ? "[логин/пароль — через безопасную форму]"
          : question || label;
        setLines((prev) => {
          let base = prev;
          if (modality === "text" && redactUser && prev.length) {
            const last = prev[prev.length - 1];
            if (last?.role === "user") {
              base = [...prev.slice(0, -1), { ...last, text: safeUserLabel }];
            }
          }
          if (modality === "voice" && (base.length === 0 || base[base.length - 1]?.text !== question)) {
            base = [...base, { role: "user" as const, text: redactUser ? safeUserLabel : question || label }];
          }
          return [
            ...base,
            {
              role: "assistant" as const,
              text: result.reply,
              sources: result.sources || [],
              pending,
              credentialForm: secretForm,
              download: download || undefined,
              suggestions: suggestions.length ? suggestions : undefined,
            },
          ];
        });
        void refreshPanels();
        return result.reply;
      } catch {
        setError("Hermes недоступен. Проверьте API и соединение.");
        return null;
      } finally {
        setSending(false);
      }
    },
    [token, conversationId, sending, refreshPanels, clearPending],
  );

  const { voiceActive, voicePhase, toggleVoice, audioRef } = useOperatorVoice(
    useCallback((text) => sendText(text, "voice").then((r) => r || ""), [sendText]),
    token,
  );

  const {
    dictating,
    supported: dictateSupported,
    error: dictateError,
    stop: stopDictate,
    toggle: toggleDictate,
    clearError: clearDictateError,
  } = useDictateToInput(
    useCallback((text) => {
      setMessage(text);
    }, []),
    token,
  );

  const [historyReady, setHistoryReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function restore() {
      try {
        const saved = typeof window !== "undefined" ? localStorage.getItem("hermes_conversation_id") : null;
        const convs = await apiConversations(token, 30);
        const preferred =
          (saved && convs.items.find((c) => c.id === saved)) ||
          convs.items.find((c) => c.channel === "hermes") ||
          convs.items.find((c) => c.channel === "cabinet" || c.channel === "operator");
        if (!preferred || cancelled) {
          setHistoryReady(true);
          return;
        }
        const msgs = await apiConversationMessages(token, preferred.id);
        if (cancelled) return;
        setConversationId(preferred.id);
        localStorage.setItem("hermes_conversation_id", preferred.id);
        const restored: ChatLine[] = (msgs.items || [])
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((m) => ({
            role: m.role as "user" | "assistant",
            text: m.body || "",
            sources:
              m.role === "assistant" && Array.isArray((m.meta as { sources?: KnowledgeSource[] } | null)?.sources)
                ? ((m.meta as { sources: KnowledgeSource[] }).sources)
                : undefined,
            suggestions:
              m.role === "assistant" &&
              Array.isArray((m.meta as { suggested_actions?: SuggestedAction[] } | null)?.suggested_actions)
                ? ((m.meta as { suggested_actions: SuggestedAction[] }).suggested_actions)
                : undefined,
          }))
          .filter((l) => l.text.trim());
        if (restored.length) {
          setLines(restored);
          setBootstrapped(true);
        }
      } catch {
        /* fresh chat */
      } finally {
        if (!cancelled) setHistoryReady(true);
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    if (!conversationId) return;
    localStorage.setItem("hermes_conversation_id", conversationId);
  }, [conversationId]);

  useEffect(() => {
    if (bootstrapped || !setup || !historyReady) return;
    setBootstrapped(true);
    if (!setup.setup_complete && lines.length === 0) {
      void sendText(
        "Я владелец офиса. Покажи статус сетапа и скажи, что сделать следующим шагом.",
        "text",
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot welcome
  }, [setup, bootstrapped, historyReady]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [lines, sending]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    stopDictate();
    const q = message.trim();
    if (!q && pendingFiles.length === 0) return;
    setMessage("");
    await sendText(q, "text", true);
  }

  function onPickFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (files?.length) addFiles(files);
    e.target.value = "";
  }

  async function openDesktopCamera() {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      cameraInputRef.current?.click();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      streamRef.current = stream;
      setCameraOpen(true);
    } catch {
      cameraInputRef.current?.click();
    }
  }

  useEffect(() => {
    if (!cameraOpen) return;
    const video = videoRef.current;
    if (video && streamRef.current) {
      video.srcObject = streamRef.current;
      void video.play().catch(() => undefined);
    }
  }, [cameraOpen]);

  function closeCamera() {
    setCameraOpen(false);
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) track.stop();
      streamRef.current = null;
    }
  }

  async function captureCameraShot() {
    const video = videoRef.current;
    if (!video) return;
    const w = video.videoWidth || 1280;
    const h = video.videoHeight || 720;
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, w, h);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
    closeCamera();
    if (!blob) {
      setError("Не удалось сделать снимок");
      return;
    }
    const file = new File([blob], `camera-${Date.now()}.jpg`, { type: "image/jpeg" });
    addFiles([file]);
  }

  useEffect(() => {
    return () => {
      clearPending(pendingRef.current);
      if (streamRef.current) {
        for (const track of streamRef.current.getTracks()) track.stop();
      }
    };
  }, [clearPending]);

  async function onConfirm() {
    if (!activePending || confirming) return;
    setConfirming(true);
    setError("");
    try {
      const result = await apiOperatorConfirm(token, activePending.tool_name, activePending.params);
      setActivePending(null);
      setLines((prev) => [
        ...prev,
        {
          role: "assistant",
          text: result.ok
            ? result.message || "Изменения применены."
            : result.message || "Не удалось применить изменения.",
        },
      ]);
      void refreshPanels();
    } catch {
      setError("Не удалось подтвердить действие.");
    } finally {
      setConfirming(false);
    }
  }

  async function onSecretSave(values: {
    login?: string;
    password?: string;
    foreign_consent?: boolean;
  }) {
    if (!activeSecretForm || secretBusy) return;
    setSecretBusy(true);
    setError("");
    try {
      const secretKind = activeSecretForm.kind || "mango_sip";
      const result = await apiTenantSecretSave(token, {
        kind: secretKind,
        login: values.login,
        password: values.password,
        foreign_consent: values.foreign_consent,
      });
      setActiveSecretForm(null);
      const probe = result.sip_probe;
      const cloud = result.cloud_probe;
      const ack =
        result.message ||
        `Сохранил ${result.kind}: ${result.login_masked || "••••"}. Пароль в чат не попал.`;
      const probeLine = probe?.message_ru
        ? `\nАвтотест линии: ${probe.message_ru}`
        : cloud?.message_ru
          ? `\nОблако: ${cloud.message_ru}`
          : "";
      setLines((prev) => [...prev, { role: "assistant", text: `${ack}${probeLine}` }]);
      void refreshPanels();
      // Follow-up in the same thread so Hermes re-reads vault + setup (no more loop).
      try {
        const isCloud = secretKind.startsWith("files_");
        const followAsk = isCloud
          ? cloud?.probe?.ok
            ? "Облако подключено. Какие облака подключены?"
            : "Облако сохранено. Какие облака подключены?"
          : probe?.ok
            ? "SIP сохранён и линия Registered. Что дальше — тестовый звонок или сменить голос?"
            : "SIP сохранён. Проверь регистрацию. Если Rejected — дай задание для Cursor или снова форму.";
        const follow = await apiOperatorChat(
          token,
          followAsk,
          conversationId || undefined,
          "text",
          "hermes",
        );
        if (follow.conversation_id) setConversationId(follow.conversation_id);
        setLines((prev) => [
          ...prev,
          { role: "user", text: "SIP сохранён. Телефон настроен? Что дальше по линии?" },
          {
            role: "assistant",
            text: follow.reply || "Проверил сейф и сетап.",
            sources: dedupeSources(follow.sources),
          },
        ]);
        const secretForm = (follow.pending_credential_form || null) as ApiCredentialFormSpec | null;
        if (secretForm) setActiveSecretForm(secretForm);
        void refreshPanels();
      } catch {
        /* ack already shown; follow-up is best-effort */
      }
    } catch {
      setError("Не удалось сохранить SIP-данные. Проверьте сессию и повторите.");
    } finally {
      setSecretBusy(false);
    }
  }

  function onMicToggle(e: React.SyntheticEvent) {
    e.preventDefault();
    e.stopPropagation();
    clearDictateError();
    toggleDictate(messageRef.current);
  }

  function dedupeSources(sources: KnowledgeSource[] | undefined): KnowledgeSource[] {
    if (!sources?.length) return [];
    const seen = new Set<string>();
    const out: KnowledgeSource[] = [];
    for (const s of sources) {
      const key = String(s.document_id || s.citation || s.title || "").trim().toLowerCase();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(s);
    }
    return out;
  }

  const progressPct = setup
    ? Math.round(
        (100 * (setup.progress?.required_done || 0)) /
          Math.max(1, setup.progress?.required_total || 1),
      )
    : 0;

  function formatCheckDetail(detail: unknown): string {
    if (detail == null) return "готово";
    if (typeof detail === "string" || typeof detail === "number" || typeof detail === "boolean") {
      return String(detail);
    }
    if (typeof detail === "object") {
      const obj = detail as Record<string, unknown>;
      if (typeof obj.message === "string") return obj.message;
      if (typeof obj.detail === "string") return obj.detail;
      if (typeof obj.kind === "string") return String(obj.kind);
    }
    return "готово";
  }

  const statusHint = dictating
    ? compact
      ? "Диктовка… tap stop"
      : "Диктовка… нажмите mic ещё раз, чтобы остановить"
    : voicePhase === "listen"
      ? "Слушаю…"
      : voicePhase === "think"
        ? "Думаю…"
        : voicePhase === "speak"
          ? compact
            ? "Говорю…"
            : "Отвечаю голосом…"
          : voicePhase === "error"
            ? "Ошибка mic"
            : sending
              ? "Печатает…"
              : compact
                ? "Чат · mic · фото"
                : dictateSupported
                  ? "Напишите, приложите фото или нажмите mic"
                  : "Напишите, приложите фото или файл";

  const canSend = !sending && (Boolean(message.trim()) || pendingFiles.length > 0);

  return (
    <div
      className="operator-stage hermes-stage hx-app"
      ref={mountRef}
      data-voice-active={voiceActive ? "true" : "false"}
      data-compact={compact ? "1" : "0"}
    >
      <header className="hx-topbar">
        <div className="hx-brand">
          <HermesAvatar />
          <div>
            <strong>Hermes</strong>
            <small>{statusHint}</small>
          </div>
        </div>
        <div className="hx-top-actions">
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="outline"
                  size="icon"
                  className={cn("hx-top-btn", voiceActive && "border-sky-400/60 bg-sky-50")}
                  onClick={toggleVoice}
                  aria-label="Голосовой диалог"
                />
              }
            >
              <Mic size={compact ? 16 : 18} />
            </TooltipTrigger>
            <TooltipContent>Голосовой диалог</TooltipContent>
          </Tooltip>
          {!compact && (
            <div className="hx-orb-mini" aria-hidden>
              <CrystalOrb voiceActive={voiceActive} voicePhase={voicePhase} onOrbClick={toggleVoice} />
            </div>
          )}
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="outline"
                  size="icon"
                  className="hx-top-btn relative"
                  onClick={() => setPanelOpen(true)}
                  aria-label="Панель офиса"
                />
              }
            >
              <PanelRight size={compact ? 16 : 18} />
              {!setup?.setup_complete && <i className="hx-dot" />}
              {health && !health.healthy && <i className="hx-dot warn" />}
            </TooltipTrigger>
            <TooltipContent>Офис: сетап и здоровье</TooltipContent>
          </Tooltip>
        </div>
      </header>

      <div className="hx-body">
        <main className="hx-chat">
          <ScrollArea className="hx-thread-scroll h-full min-h-0 flex-1">
            <div className="hx-thread">
              {lines.length === 0 && !sending && (
                <div className="hx-empty">
                  {!compact && <p className="hx-empty-kicker">DELNO · office agent</p>}
                  <h1 className="hx-empty-title">Hermes</h1>
                  <p className="hx-empty-lead">
                    {compact
                      ? "Задача, фото или mic — ответ здесь."
                      : "Диалог сохраняется: после обновления страницы Hermes помнит этот тред. Пишите задачу, кидайте фото или нажмите mic."}
                  </p>
                  <div className={cn("hx-suggestions", compact && "hx-suggestions-chips")}>
                    {QUICK_PROMPTS.map((item) => (
                      <Button
                        key={item.title}
                        type="button"
                        variant="outline"
                        disabled={sending}
                        className={cn(
                          "h-auto whitespace-normal text-left",
                          compact
                            ? "rounded-full px-3.5 py-2 text-[13px] font-semibold"
                            : "flex-col items-start gap-1 px-3.5 py-3",
                        )}
                        onClick={() => void sendText(item.text)}
                      >
                        <strong className="text-[13px] font-semibold">{item.title}</strong>
                        {!compact && (
                          <span className="text-muted-foreground text-xs font-normal leading-snug">
                            {item.text}
                          </span>
                        )}
                      </Button>
                    ))}
                  </div>
                </div>
              )}

              {lines.map((line, idx) =>
                line.role === "user" ? (
                  <article key={idx} className="hx-row hx-row-user">
                    <div className="hx-bubble hx-bubble-user">
                      {line.previews && line.previews.length > 0 && (
                        <div className="hx-previews">
                          {line.previews.map((p) => (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img key={p.url} src={p.url} alt={p.name} />
                          ))}
                        </div>
                      )}
                      <div className="hx-text">{line.text}</div>
                    </div>
                  </article>
                ) : (
                  <article key={idx} className="hx-row hx-row-assistant">
                    {!compact && <HermesAvatar />}
                    <div className="hx-assistant-col">
                      <div className="hx-bubble hx-bubble-assistant">
                        <div className="hx-text">{line.text}</div>
                        {(() => {
                          const sources = dedupeSources(line.sources);
                          if (!sources.length) return null;
                          return (
                            <p className="hx-sources-meta" title="Источники ответа (не кнопки)">
                              Источники:{" "}
                              {sources
                                .map((s) => s.title || s.citation || s.document_id)
                                .filter(Boolean)
                                .slice(0, 4)
                                .join(" · ")}
                            </p>
                          );
                        })()}
                      </div>
                      {line.suggestions && line.suggestions.length > 0 && (
                        <div className="hx-action-chips">
                          {line.suggestions.map((a) => (
                            <Button
                              key={`${a.title}-${a.text}`}
                              type="button"
                              variant="outline"
                              size="sm"
                              disabled={sending}
                              className="h-auto rounded-full px-3 py-1.5 text-[12px] font-semibold"
                              onClick={() => void sendText(a.text)}
                            >
                              {a.title}
                            </Button>
                          ))}
                        </div>
                      )}
                      {line.download?.body ? (
                        <div className="hx-action-chips">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-auto rounded-full px-3 py-1.5 text-[12px] font-semibold"
                            onClick={() => triggerMarkdownDownload(line.download!)}
                          >
                            Скачать {line.download.filename || "шаблон.md"}
                          </Button>
                        </div>
                      ) : null}
                      {line.credentialForm &&
                      activeSecretForm?.kind === line.credentialForm.kind ? (
                        <CredentialFormCard
                          form={activeSecretForm}
                          busy={secretBusy}
                          onSubmit={onSecretSave}
                          onCancel={() => setActiveSecretForm(null)}
                        />
                      ) : line.credentialForm ? (
                        <p className="hx-confirm-expired">
                          Форма уже закрыта — напишите «пришли форму» или «подключи Яндекс.Диск».
                        </p>
                      ) : null}
                      {line.pending && activePending?.confirmation_id === line.pending.confirmation_id ? (
                        <ConfirmCard
                          summary={line.pending.summary}
                          toolName={line.pending.tool_name}
                          busy={confirming}
                          onConfirm={() => void onConfirm()}
                          onCancel={() => setActivePending(null)}
                        />
                      ) : line.pending ? (
                        <p className="hx-confirm-expired">Подтверждение уже неактивно — повторите запрос.</p>
                      ) : null}
                    </div>
                  </article>
                ),
              )}

              {sending && (
                <article className="hx-row hx-row-assistant">
                  {!compact && <HermesAvatar />}
                  <div className="hx-bubble hx-bubble-assistant hx-typing" aria-label="Печатает">
                    <span />
                    <span />
                    <span />
                  </div>
                </article>
              )}
              <div ref={threadEndRef} />
            </div>
          </ScrollArea>

          <div className="hx-composer-wrap">
            {(error || dictateError) && <p className="hx-error">{error || dictateError}</p>}

            {pendingFiles.length > 0 && (
              <div className="hx-attach-strip">
                {pendingFiles.map((item) => (
                  <div key={item.id} className="hx-attach-chip" data-kind={item.kind}>
                    {item.previewUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={item.previewUrl} alt={item.filename} />
                    ) : (
                      <span>{item.filename}</span>
                    )}
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      className="absolute top-1 right-1 rounded-full bg-black/70 text-white hover:bg-black/80 hover:text-white"
                      aria-label="Убрать вложение"
                      onClick={() => removePending(item.id)}
                      disabled={sending}
                    >
                      <X size={14} />
                    </Button>
                  </div>
                ))}
              </div>
            )}

            <form className="hx-composer" onSubmit={onSubmit}>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*,.pdf,.docx,.xlsx,.csv,.txt,.md,.html,.json"
                multiple
                hidden
                onChange={onPickFiles}
              />
              <input
                ref={cameraInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                hidden
                onChange={onPickFiles}
              />
              <div className="hx-composer-tools">
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        disabled={sending}
                        onClick={() => fileInputRef.current?.click()}
                        aria-label="Прикрепить"
                        className="hx-tool-btn"
                      />
                    }
                  >
                    <Paperclip size={compact ? 16 : 18} />
                  </TooltipTrigger>
                  <TooltipContent>Файл или фото</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        disabled={sending}
                        onClick={() => void openDesktopCamera()}
                        aria-label="Камера"
                        className="hx-tool-btn"
                      />
                    }
                  >
                    <Camera size={compact ? 16 : 18} />
                  </TooltipTrigger>
                  <TooltipContent>Снимок с камеры</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        type="button"
                        variant={dictating ? "default" : "ghost"}
                        size="icon"
                        disabled={sending || !dictateSupported}
                        aria-label={dictating ? "Остановить диктовку" : "Диктовка"}
                        aria-pressed={dictating}
                        onClick={onMicToggle}
                        onContextMenu={(e) => e.preventDefault()}
                        className="hx-tool-btn touch-none"
                      />
                    }
                  >
                    <Mic size={compact ? 16 : 18} />
                  </TooltipTrigger>
                  <TooltipContent>
                    {dictateSupported
                      ? dictating
                        ? "Нажмите, чтобы остановить"
                        : "Нажмите, чтобы диктовать"
                      : "Диктовка недоступна в этом браузере"}
                  </TooltipContent>
                </Tooltip>
              </div>
              <Textarea
                ref={textareaRef}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder={compact ? "Сообщение…" : "Сообщение Hermes…"}
                disabled={sending}
                rows={1}
                className={cn(
                  "max-h-40 flex-1 resize-none border-0 bg-transparent px-1 shadow-none focus-visible:ring-0",
                  compact ? "min-h-8 py-1.5 text-[15px]" : "min-h-9 py-2",
                )}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    if (canSend) {
                      stopDictate();
                      const q = message.trim();
                      setMessage("");
                      void sendText(q, "text", true);
                    }
                  }
                }}
              />
              <Button
                type="submit"
                size="icon"
                className={cn("hx-send-shadcn rounded-[14px]", compact ? "size-9" : "size-10")}
                disabled={!canSend}
                aria-label="Отправить"
              >
                <ArrowUp size={compact ? 16 : 18} strokeWidth={2.4} />
              </Button>
            </form>
            {!compact && (
              <p className="hx-footnote">Enter — отправить · Shift+Enter — новая строка</p>
            )}
          </div>
        </main>
      </div>

      <Sheet open={panelOpen} onOpenChange={setPanelOpen}>
        <SheetContent
          side={compact ? "bottom" : "right"}
          className={cn(
            "gap-0 p-0",
            compact
              ? "hx-office-sheet h-[min(78dvh,640px)] rounded-t-2xl border-t sm:max-w-none"
              : "w-[min(360px,92vw)] sm:max-w-sm",
          )}
        >
          <SheetHeader className={cn("border-b border-border/70", compact && "px-4 py-3")}>
            <SheetTitle
              className={cn(
                "font-[Fraunces,Georgia,serif] font-medium tracking-tight",
                compact ? "text-lg" : "text-xl",
              )}
            >
              Офис
            </SheetTitle>
            {!compact && (
              <SheetDescription>
                Онбординг → знания → тулзы → поручения
                {nousStatus?.enabled ? " · Nous" : " · DIY fallback"}
              </SheetDescription>
            )}
          </SheetHeader>
          <ScrollArea className={compact ? "h-[calc(100%-3.5rem)]" : "h-[calc(100%-5rem)]"}>
            <div className={cn("flex flex-col gap-3", compact ? "p-3 pb-6" : "p-4")}>
              <section className="hx-card">
                <header>
                  <span>Путь офиса</span>
                  {officeLoop?.next_step ? (
                    <Badge variant="secondary">{officeLoop.phase}</Badge>
                  ) : null}
                </header>
                {officeLoop ? (
                  <>
                    <p>{officeLoop.ui?.headline || "Настройка офиса"}</p>
                    <ul className="hermes-checklist">
                      {(officeLoop.steps || []).map((step) => (
                        <li key={step.id} data-done={step.done ? "1" : "0"}>
                          <span className="hermes-check-dot" />
                          <div>
                            <strong>{step.title}</strong>
                            <small>{step.done ? "готово" : step.hint}</small>
                          </div>
                        </li>
                      ))}
                    </ul>
                    {officeLoop.ui?.primary_cta ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="mt-2 w-full"
                        disabled={sending}
                        onClick={() => {
                          setPanelOpen(false);
                          void sendText(officeLoop.ui!.primary_cta!.text);
                        }}
                      >
                        {officeLoop.ui.primary_cta.title}
                      </Button>
                    ) : null}
                    {officeLoop.kb_draft?.status === "draft" ? (
                      <p className="mt-2 text-xs text-muted-foreground">
                        Черновик KB «{officeLoop.kb_draft.title}» ждёт подтверждения в чате.
                      </p>
                    ) : null}
                  </>
                ) : (
                  <p>Загружаю путь…</p>
                )}
              </section>

              <section className="hx-card">
                <header>
                  <span>Поручения</span>
                  <Badge variant="secondary">{agentTasks.length}</Badge>
                </header>
                {agentTasks.length ? (
                  <ul className="hermes-checklist">
                    {agentTasks.slice(0, 5).map((t) => (
                      <li key={t.id} data-done={t.status === "completed" ? "1" : "0"}>
                        <span className="hermes-check-dot" />
                        <div>
                          <strong>{t.trigger_kind}</strong>
                          <small>
                            {t.status} · {t.goal.slice(0, 80)}
                          </small>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground text-sm">Пока нет сохранённых поручений.</p>
                )}
              </section>

              <section className="hx-card">
                <header>
                  <span>Сетап</span>
                  {setup?.setup_complete ? (
                    <CheckCircle2 size={15} className="hermes-ok" />
                  ) : (
                    <Badge variant="secondary">{progressPct}%</Badge>
                  )}
                </header>
                {setup ? (
                  <>
                    <div className="hermes-progress-bar" aria-hidden>
                      <i style={{ width: `${progressPct}%` }} />
                    </div>
                    <p>{setup.message_ru}</p>
                    <ul className="hermes-checklist">
                      {(setup.steps || []).map((step) => {
                        const check = (setup.checks || {})[step.id];
                        const done = Boolean(check?.ok);
                        const optional = Boolean(check?.optional);
                        return (
                          <li key={step.id} data-done={done ? "1" : "0"} data-optional={optional ? "1" : "0"}>
                            <span className="hermes-check-dot" />
                            <div>
                              <strong>
                                {step.title}
                                {optional ? " · опц." : ""}
                              </strong>
                              <small>
                                {done ? formatCheckDetail(check?.detail) : step.hint || "нужно сделать"}
                              </small>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </>
                ) : (
                  <p>Загружаю…</p>
                )}
              </section>

              <section className="hx-card">
                <header>
                  <span>Здоровье</span>
                  {health && !health.healthy && <AlertTriangle size={15} className="hermes-warn" />}
                  {health?.healthy && <CheckCircle2 size={15} className="hermes-ok" />}
                </header>
                {health ? (
                  <>
                    <p>{health.message_ru}</p>
                    {(health.alerts || []).length > 0 && (
                      <ul className="hermes-alerts">
                        {(health.alerts || []).slice(0, 5).map((a) => (
                          <li key={a.code} data-sev={a.severity}>
                            <strong>{a.message_ru}</strong>
                            {a.fix ? <small>{a.fix}</small> : null}
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                ) : (
                  <p>Проверяю…</p>
                )}
              </section>

              <section className="hx-card">
                <header>
                  <span>Затраты</span>
                </header>
                {billing ? (
                  <>
                    <p>{billing.message_ru}</p>
                    <ul className="hermes-calls">
                      <li>
                        <strong>
                          {billing.llm?.tokens_total?.toLocaleString("ru-RU") ?? "0"} ток.
                        </strong>
                        <small>
                          in {billing.llm?.prompt_tokens?.toLocaleString("ru-RU") ?? 0} / out{" "}
                          {billing.llm?.completion_tokens?.toLocaleString("ru-RU") ?? 0}
                        </small>
                      </li>
                      <li>
                        <strong>${(billing.llm?.cost_vendor_usd ?? 0).toFixed(4)}</strong>
                        <small>себестоимость OpenAI</small>
                      </li>
                      <li>
                        <strong>
                          {(billing.llm?.cost_client_rub ?? 0).toFixed(2)}{" "}
                          {billing.balance?.currency || "RUB"}
                        </strong>
                        <small>
                          клиенту · баланс {(billing.balance?.token_credits ?? 0).toFixed(2)}
                        </small>
                      </li>
                    </ul>
                  </>
                ) : (
                  <p>Загружаю…</p>
                )}
              </section>

              <Separator />

              <section className="hx-card">
                <header>
                  <span>Каналы</span>
                </header>
                <p>Токен бота или QR. Instagram — тот же контур.</p>
                <div className="hx-channel-row">
                  <Button type="button" variant="secondary" size="sm" disabled={qrBusy} onClick={() => void startQr("telegram")}>
                    QR TG
                  </Button>
                  <Button type="button" variant="secondary" size="sm" disabled={qrBusy} onClick={() => void startQr("max")}>
                    QR MAX
                  </Button>
                  <Button type="button" variant="secondary" size="sm" disabled={qrBusy} onClick={() => void startQr("instagram")}>
                    QR IG
                  </Button>
                </div>
              </section>

              {calls.length > 0 && (
                <section className="hx-card">
                  <header>
                    <span>Звонки</span>
                  </header>
                  <ul className="hermes-calls">
                    {calls.map((c) => (
                      <li key={c.id}>
                        <strong>
                          {c.direction} · {c.state}
                        </strong>
                        <small>
                          {(c.from_e164 || "—") + " → " + (c.to_e164 || "—")}
                        </small>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          </ScrollArea>
        </SheetContent>
      </Sheet>

      {cameraOpen && (
        <div className="hermes-camera-modal" role="dialog" aria-label="Камера">
          <div className="hermes-camera-card">
            <video ref={videoRef} playsInline muted autoPlay />
            <div className="hermes-camera-actions">
              <Button type="button" variant="outline" onClick={closeCamera}>
                Отмена
              </Button>
              <Button type="button" onClick={() => void captureCameraShot()}>
                Снять
              </Button>
            </div>
          </div>
        </div>
      )}

      <audio ref={audioRef} className="operator-audio" preload="none" playsInline />
    </div>
  );
}
