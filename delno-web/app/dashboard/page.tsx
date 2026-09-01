"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { apiConversations, apiLeadsList, apiTenantLegalGet } from "@/lib/api";
import { card, colors } from "@/lib/ui";

export default function DashboardOverviewPage() {
  const { token } = useRequireAuth();
  const [stats, setStats] = useState({ leads: 0, conversations: 0, hasLegal: false });

  useEffect(() => {
    if (!token) return;
    Promise.all([apiLeadsList(token, 100), apiConversations(token, 100), apiTenantLegalGet(token)])
      .then(([leads, convs, legal]) => {
        setStats({
          leads: leads.items.length,
          conversations: convs.items.length,
          hasLegal: Boolean(legal.legal?.inn),
        });
      })
      .catch(() => undefined);
  }, [token]);

  return (
    <>
      <h1 style={{ margin: "0 0 8px", fontSize: 28 }}>Обзор</h1>
      <p style={{ margin: "0 0 28px", color: colors.muted }}>Заявки, диалоги и юридический профиль tenant</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 16 }}>
        <StatCard title="Заявки" value={String(stats.leads)} href="/dashboard/leads" />
        <StatCard title="Диалоги" value={String(stats.conversations)} href="/dashboard/inbox" />
        <StatCard title="Юр. профиль" value={stats.hasLegal ? "Заполнен" : "Не задан"} href="/dashboard/settings" />
      </div>
      <section style={{ ...card, marginTop: 24 }}>
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Быстрые действия</h2>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
          <Link href="/dashboard/operator" style={{ color: colors.accent }}>
            Спросить Operator по базе знаний →
          </Link>
          <Link href="/dashboard/settings" style={{ color: colors.accent }}>
            Указать ИНН компании →
          </Link>
        </div>
      </section>
    </>
  );
}

function StatCard({ title, value, href }: { title: string; value: string; href: string }) {
  return (
    <Link href={href} style={{ textDecoration: "none", color: "inherit" }}>
      <div style={{ ...card, minHeight: 100 }}>
        <div style={{ fontSize: 12, color: colors.muted, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          {title}
        </div>
        <div style={{ fontSize: 32, fontWeight: 800, marginTop: 8 }}>{value}</div>
      </div>
    </Link>
  );
}
