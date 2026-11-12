"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useRequireAuth } from "@/lib/auth";
import {
  apiConversationDelete,
  apiConversations,
  apiConversationsBulkDelete,
  type ConversationItem,
} from "@/lib/api";
import { DashboardFrame } from "@/components/DashboardFrame";
import { InboxPanel } from "@/components/InboxPanel";

export default function InboxLayout({ children }: { children: React.ReactNode }) {
  const { token } = useRequireAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [items, setItems] = useState<ConversationItem[]>([]);
  const [newCount, setNewCount] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [busyId, setBusyId] = useState<string | null>(null);

  const activeId = pathname.match(/\/dashboard\/inbox\/([^/]+)/)?.[1];

  const reload = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await apiConversations(token, 100, query, filter === "all" ? undefined : filter);
      setItems(data.items);
      setNewCount(data.new_count ?? 0);
      setError("");
    } catch {
      setError("Не удалось загрузить диалоги");
    } finally {
      setLoading(false);
    }
  }, [token, query, filter]);

  useEffect(() => {
    if (!token) return;
    const t = window.setTimeout(() => {
      void reload();
    }, query ? 250 : 0);
    return () => window.clearTimeout(t);
  }, [token, query, filter, reload]);

  async function onDelete(id: string) {
    if (!token) return;
    setBusyId(id);
    try {
      await apiConversationDelete(token, id);
      setItems((prev) => prev.filter((i) => i.id !== id));
      if (activeId === id) router.push("/dashboard/inbox");
    } catch {
      setError("Не удалось удалить диалог");
    } finally {
      setBusyId(null);
    }
  }

  async function onCleanupJunk() {
    if (!token) return;
    if (
      !window.confirm(
        "Удалить старые Hermes-диалоги и оставить только самый свежий? Widget/звонки не трогаем.",
      )
    ) {
      return;
    }
    setBusyId("bulk");
    try {
      await apiConversationsBulkDelete(token, { channel: "hermes", keep_latest_hermes: true });
      await reload();
      if (activeId) router.push("/dashboard/inbox");
    } catch {
      setError("Не удалось очистить мусор");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <DashboardFrame
      inboxSlot={
        <InboxPanel
          items={items}
          activeId={activeId}
          error={error}
          loading={loading}
          newCount={newCount}
          query={query}
          filter={filter}
          busyId={busyId}
          onQueryChange={setQuery}
          onFilterChange={setFilter}
          onDelete={(id) => void onDelete(id)}
          onCleanupJunk={() => void onCleanupJunk()}
        />
      }
    >
      {children}
    </DashboardFrame>
  );
}
