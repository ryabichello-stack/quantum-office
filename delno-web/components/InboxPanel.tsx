"use client";

import Link from "next/link";
import { useState } from "react";
import { Globe, Mail, MessageCircle, Phone, Search, Send, X } from "lucide-react";
import type { ConversationItem } from "@/lib/api";

function channelMeta(channel: string) {
  const c = channel.toLowerCase();
  if (c.includes("phone") || c.includes("call")) return { tone: "phone", Icon: Phone };
  if (c.includes("mail") || c.includes("email")) return { tone: "mail", Icon: Mail };
  if (c.includes("telegram")) return { tone: "chat", Icon: Send };
  if (c.includes("web") || c.includes("site") || c.includes("widget")) return { tone: "web", Icon: Globe };
  return { tone: "chat", Icon: MessageCircle };
}

function formatTime(iso: string | null | undefined) {
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

function displayName(row: ConversationItem) {
  if (row.visitor_name) return row.visitor_name;
  if (row.contact_ref) return row.contact_ref;
  if (row.channel_label?.includes("сайт")) return "Новый посетитель";
  return row.channel_label || row.channel;
}

function previewText(row: ConversationItem) {
  if (row.last_message_preview) return row.last_message_preview;
  if (row.lead_id) return "есть заявка";
  return row.status;
}

export function InboxPanel({
  items,
  activeId,
  error,
  loading,
  newCount = 0,
  query,
  filter,
  onQueryChange,
  onFilterChange,
}: {
  items: ConversationItem[];
  activeId?: string;
  error?: string;
  loading?: boolean;
  newCount?: number;
  query?: string;
  filter?: string;
  onQueryChange?: (q: string) => void;
  onFilterChange?: (f: string) => void;
}) {
  const [searchOpen, setSearchOpen] = useState(Boolean(query?.trim()));
  const activeFilter = filter || "all";

  return (
    <section className="inbox">
      <div className="inbox-title">
        <div>
          <small>Рабочее пространство</small>
          <b>Диалоги</b>
        </div>
        <button
          type="button"
          aria-label="Поиск"
          className={searchOpen ? "inbox-search-toggle active" : "inbox-search-toggle"}
          onClick={() => setSearchOpen((v) => !v)}
        >
          <Search />
        </button>
      </div>

      {searchOpen && (
        <div className="inbox-search">
          <Search />
          <input
            value={query || ""}
            onChange={(e) => onQueryChange?.(e.target.value)}
            placeholder="Имя, телефон, сообщение…"
            aria-label="Поиск диалогов"
          />
          {query?.trim() ? (
            <button type="button" aria-label="Очистить" onClick={() => onQueryChange?.("")}>
              <X />
            </button>
          ) : null}
        </div>
      )}

      <div className="inbox-filter">
        <button
          type="button"
          className={activeFilter === "all" ? "active" : undefined}
          onClick={() => onFilterChange?.("all")}
        >
          <b>
            Все <span>{items.length}</span>
          </b>
        </button>
        <button
          type="button"
          className={activeFilter === "new" ? "active" : undefined}
          onClick={() => onFilterChange?.("new")}
        >
          Новые {newCount > 0 ? newCount : ""}
        </button>
        <button
          type="button"
          className={activeFilter === "mine" ? "active" : undefined}
          onClick={() => onFilterChange?.("mine")}
        >
          Operator
        </button>
      </div>

      {error && <p className="inbox-empty inbox-error">{error}</p>}
      {loading && <p className="inbox-empty">Загрузка…</p>}
      {!loading && !error && items.length === 0 && <p className="inbox-empty">Диалогов пока нет</p>}
      {items.map((row) => {
        const { tone, Icon } = channelMeta(row.channel);
        const hot = activeId === row.id;
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
              <b>{displayName(row)}</b>
              <p>{previewText(row)}</p>
            </div>
            <time>{formatTime(row.updated_at || row.created_at)}</time>
          </Link>
        );
      })}
    </section>
  );
}
