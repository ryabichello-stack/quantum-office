"use client";

import Link from "next/link";
import { Globe, Mail, MessageCircle, Phone, Search, Send } from "lucide-react";
import type { ConversationItem } from "@/lib/api";

function channelMeta(channel: string) {
  const c = channel.toLowerCase();
  if (c.includes("phone") || c.includes("call")) return { tone: "phone", Icon: Phone, label: channel };
  if (c.includes("mail") || c.includes("email")) return { tone: "mail", Icon: Mail, label: channel };
  if (c.includes("telegram")) return { tone: "chat", Icon: Send, label: channel };
  if (c.includes("web") || c.includes("site")) return { tone: "web", Icon: Globe, label: channel };
  return { tone: "chat", Icon: MessageCircle, label: channel };
}

function formatTime(iso: string | null) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const diff = Date.now() - d.getTime();
    if (diff < 60_000) return "сейчас";
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} мин`;
    return d.toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export function InboxPanel({
  items,
  activeId,
  error,
  loading,
}: {
  items: ConversationItem[];
  activeId?: string;
  error?: string;
  loading?: boolean;
}) {
  return (
    <section className="inbox">
      <div className="inbox-title">
        <div>
          <small>Рабочее пространство</small>
          <b>Диалоги</b>
        </div>
        <button type="button" aria-label="Поиск">
          <Search />
        </button>
      </div>
      <div className="inbox-filter">
        <b>
          Все <span>{items.length}</span>
        </b>
        <span>Новые</span>
        <span>Мои</span>
      </div>
      {error && <p className="inbox-empty inbox-error">{error}</p>}
      {loading && <p className="inbox-empty">Загрузка…</p>}
      {!loading && !error && items.length === 0 && <p className="inbox-empty">Диалогов пока нет</p>}
      {items.map((row, index) => {
        const { tone, Icon } = channelMeta(row.channel);
        const hot = activeId === row.id || (!activeId && index === 0);
        return (
          <Link
            key={row.id}
            href={`/dashboard/inbox/${row.id}`}
            className={hot ? "inbox-row hot" : "inbox-row"}
          >
            <div className={`source ${tone}`}>
              <Icon />
            </div>
            <div>
              <b>{row.channel}</b>
              <p>{row.status}</p>
            </div>
            <time>{formatTime(row.created_at)}</time>
          </Link>
        );
      })}
    </section>
  );
}
