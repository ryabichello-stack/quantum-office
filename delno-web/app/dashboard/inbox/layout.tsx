"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useRequireAuth } from "@/lib/auth";
import { apiConversations, type ConversationItem } from "@/lib/api";
import { DashboardFrame } from "@/components/DashboardFrame";
import { InboxPanel } from "@/components/InboxPanel";

export default function InboxLayout({ children }: { children: React.ReactNode }) {
  const { token } = useRequireAuth();
  const pathname = usePathname();
  const [items, setItems] = useState<ConversationItem[]>([]);
  const [newCount, setNewCount] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");

  const activeId = pathname.match(/\/dashboard\/inbox\/([^/]+)/)?.[1];

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    const t = window.setTimeout(() => {
      apiConversations(token, 50, query, filter === "all" ? undefined : filter)
        .then((data) => {
          setItems(data.items);
          setNewCount(data.new_count ?? 0);
        })
        .catch(() => setError("Не удалось загрузить диалоги"))
        .finally(() => setLoading(false));
    }, query ? 250 : 0);
    return () => window.clearTimeout(t);
  }, [token, query, filter]);

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
          onQueryChange={setQuery}
          onFilterChange={setFilter}
        />
      }
    >
      {children}
    </DashboardFrame>
  );
}
