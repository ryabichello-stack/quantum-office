"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { apiConversations, apiLeadsList, apiTenantLegalGet } from "@/lib/api";
import { DashboardFrame } from "@/components/DashboardFrame";

export default function DashboardOverviewPage() {
  const { token } = useRequireAuth();
  const [stats, setStats] = useState({ leads: 0, conversations: 0, hasLegal: false });

  useEffect(() => {
    if (!token) return;
    Promise.all([apiLeadsList(token, 100), apiConversations(token, 100), apiTenantLegalGet(token)])
      .then(([leads, convs, legal]) => {
        setStats({
          leads: leads.items.length,
          conversations: convs.total ?? convs.items.length,
          hasLegal: Boolean(legal.legal?.inn),
        });
      })
      .catch(() => undefined);
  }, [token]);

  return (
    <DashboardFrame>
      <div className="page-head">
        <small>DELNO Кабинет</small>
        <h1>Обзор</h1>
        <p>Заявки, диалоги и юридический профиль tenant</p>
      </div>
      <div className="stat-grid">
        <Link href="/dashboard/leads" className="stat-card">
          <span>Заявки</span>
          <b>{stats.leads}</b>
          <small>из сайта и каналов</small>
        </Link>
        <Link href="/dashboard/inbox" className="stat-card">
          <span>Диалоги</span>
          <b>{stats.conversations}</b>
          <small>Operator и каналы</small>
        </Link>
        <Link href="/dashboard/knowledge" className="stat-card">
          <span>Знания</span>
          <b style={{ fontSize: 18 }}>KB</b>
          <small>текст и Operator</small>
        </Link>
        <Link href="/dashboard/settings" className="stat-card">
          <span>Юр. профиль</span>
          <b style={{ fontSize: stats.hasLegal ? 32 : 18 }}>{stats.hasLegal ? "✓" : "—"}</b>
          <small>{stats.hasLegal ? "ИНН заполнен" : "Укажите ИНН"}</small>
        </Link>
      </div>
      <div className="delno-result">
        <div className="result-head">
          <span>Быстрые действия</span>
        </div>
        <p style={{ margin: 0 }}>
          <Link href="/dashboard/operator" style={{ fontWeight: 700 }}>
            Спросить Operator →
          </Link>
          {" · "}
          <Link href="/dashboard/settings" style={{ fontWeight: 700 }}>
            Юридический профиль →
          </Link>
        </p>
      </div>
    </DashboardFrame>
  );
}
