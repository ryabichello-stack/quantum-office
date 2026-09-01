"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutGrid,
  LogOut,
  MessageCircle,
  ShieldCheck,
  Sparkles,
  UserRound,
} from "lucide-react";
import { DelnoMark } from "@/components/DelnoMark";
import { clearToken } from "@/lib/auth";
import type { TenantMe } from "@/lib/api";

const nav = [
  { href: "/dashboard", label: "Обзор", Icon: LayoutGrid, exact: true },
  { href: "/dashboard/inbox", label: "Диалоги", Icon: MessageCircle },
  { href: "/dashboard/leads", label: "Заявки", Icon: UserRound },
  { href: "/dashboard/operator", label: "Operator", Icon: Sparkles },
  { href: "/dashboard/settings", label: "Настройки", Icon: ShieldCheck },
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

  return (
    <div className="cabinet-app">
      <div className="v2-console">
        <div className="console-bar">
          <div className="traffic">
            <i />
            <i />
            <i />
          </div>
          <span>{hostLabel}</span>
          <div className="console-avatar">{(me?.tenant_slug || "D").slice(0, 1).toUpperCase()}</div>
        </div>
        <div className={`console-shell cabinet-shell${withInbox ? " with-inbox" : ""}`}>
          <aside>
            <Link href="/dashboard" className="side-logo" aria-label="DELNO">
              <DelnoMark small />
            </Link>
            {nav.map(({ href, label, Icon, exact }) => {
              const active = exact
                ? pathname === href
                : pathname === href || pathname.startsWith(`${href}/`);
              return (
                <Link
                  key={href}
                  href={href}
                  className={active ? "selected" : undefined}
                  aria-label={label}
                  title={label}
                >
                  <Icon />
                </Link>
              );
            })}
            <div className="side-bottom">
              <button
                type="button"
                aria-label="Выйти"
                title="Выйти"
                onClick={() => {
                  clearToken();
                  router.push("/");
                }}
              >
                <LogOut />
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
