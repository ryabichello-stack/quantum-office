"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  FileText,
  LogOut,
  MessageCircle,
  Settings2,
  Sparkles,
  UserRound,
  Wallet,
} from "lucide-react";
import { DelnoMark } from "@/components/DelnoMark";
import { clearToken } from "@/lib/auth";
import type { TenantMe } from "@/lib/api";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/dashboard/hermes", label: "Hermes", hint: "Главный помощник", Icon: Sparkles, primary: true },
  { href: "/dashboard/inbox", label: "Диалоги", hint: "Переписки и звонки", Icon: MessageCircle },
  { href: "/dashboard/leads", label: "Заявки", hint: "Лиды с сайта", Icon: UserRound },
  { href: "/dashboard/knowledge", label: "Знания", hint: "База ответов", Icon: FileText },
  { href: "/dashboard/billing", label: "Затраты", hint: "Токены и деньги", Icon: Wallet },
];

export function AppShell({
  me,
  children,
  inboxSlot,
  hostLabel = "app.dlno.ru",
}: {
  me: TenantMe | null;
  children: React.ReactNode;
  inboxSlot?: React.ReactNode;
  hostLabel?: string;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const withInbox = Boolean(inboxSlot);
  const company = me?.tenant_name || me?.tenant_slug || "DELNO";

  return (
    <div className="cabinet-app hx-shell-root">
      <div className="v2-console hx-console">
        <div className="console-bar hx-console-bar">
          <div className="traffic">
            <i />
            <i />
            <i />
          </div>
          <span>{hostLabel}</span>
          <div className="console-avatar" title={company}>
            {company.slice(0, 1).toUpperCase()}
          </div>
        </div>
        <div className={cn("console-shell cabinet-shell hx-shell", withInbox && "with-inbox")}>
          <aside className="hx-nav" aria-label="Разделы кабинета">
            <Link href="/dashboard/hermes" className="hx-nav-brand" aria-label="DELNO — к Hermes">
              <DelnoMark small />
              <span>
                <strong>DELNO</strong>
                <small>{company}</small>
              </span>
            </Link>

            <nav className="hx-nav-list">
              {nav.map(({ href, label, hint, Icon, primary }) => {
                const active =
                  pathname === href ||
                  pathname.startsWith(`${href}/`) ||
                  (href === "/dashboard/hermes" &&
                    (pathname === "/dashboard" || pathname.startsWith("/dashboard/operator")));
                return (
                  <Link
                    key={href}
                    href={href}
                    className={cn("hx-nav-item", active && "is-active", primary && "is-primary")}
                    title={hint}
                  >
                    <Icon size={18} strokeWidth={2.1} />
                    <span className="hx-nav-copy">
                      <b>{label}</b>
                      <small>{hint}</small>
                    </span>
                  </Link>
                );
              })}
            </nav>

            <div className="hx-nav-bottom">
              <Link
                href="/dashboard/settings"
                className={cn("hx-nav-item", pathname.startsWith("/dashboard/settings") && "is-active")}
                title="Настройки кабинета"
              >
                <Settings2 size={18} strokeWidth={2.1} />
                <span className="hx-nav-copy">
                  <b>Настройки</b>
                  <small>Каналы и профиль</small>
                </span>
              </Link>
              <button
                type="button"
                className="hx-nav-item hx-nav-logout"
                title="Выйти"
                onClick={() => {
                  clearToken();
                  router.push("/");
                }}
              >
                <LogOut size={18} strokeWidth={2.1} />
                <span className="hx-nav-copy">
                  <b>Выйти</b>
                  <small>Сменить аккаунт</small>
                </span>
              </button>
            </div>
          </aside>
          {inboxSlot}
          <section className="conversation cabinet-main">{children}</section>
        </div>
      </div>
    </div>
  );
}
