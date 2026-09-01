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
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const activeId = pathname.match(/\/dashboard\/inbox\/([^/]+)/)?.[1];

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    apiConversations(token)
      .then((data) => setItems(data.items))
      .catch(() => setError("Не удалось загрузить диалоги"))
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <DashboardFrame inboxSlot={<InboxPanel items={items} activeId={activeId} error={error} loading={loading} />}>
      {children}
    </DashboardFrame>
  );
}
