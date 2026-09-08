"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { apiConversations, apiLeadsList, apiOnboardingStatus, apiTenantLegalGet } from "@/lib/api";
import { DashboardFrame } from "@/components/DashboardFrame";

export default function DashboardOverviewPage() {
  const { token } = useRequireAuth();
  const [stats, setStats] = useState({ leads: 0, conversations: 0, hasLegal: false });
  const [onboardingStatus, setOnboardingStatus] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([
      apiLeadsList(token, 100),
      apiConversations(token, 100),
      apiTenantLegalGet(token),
      apiOnboardingStatus(token).catch(() => null),
    ])
      .then(([leads, convs, legal, onboarding]) => {
        setStats({
          leads: leads.items.length,
          conversations: convs.total ?? convs.items.length,
          hasLegal: Boolean(legal.legal?.inn),
        });
        setOnboardingStatus(onboarding?.status || null);
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
      {onboardingStatus && onboardingStatus !== "published" && (
        <div className="delno-result onboarding-banner" style={{ marginBottom: 16 }}>
          <div className="result-head">
            <span>Настройка DELNO</span>
          </div>
          <p style={{ margin: 0 }}>
            Продолжите разговор с DELNO — расскажите о бизнесе или пришлите сайт.{" "}
            <Link href="/dashboard/onboarding" style={{ fontWeight: 700 }}>
              Перейти к onboarding →
            </Link>
          </p>
        </div>
      )}
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
