"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Building2, FileText, KeyRound, LogOut } from "lucide-react";
import { DelnoMark } from "@/components/DelnoMark";
import { ADMIN_TOKEN_KEY } from "@/lib/api";

const nav = [
  { href: "/tenants", label: "Клиенты", Icon: Building2 },
  { href: "/settings", label: "Секреты", Icon: KeyRound },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  function logout() {
    localStorage.removeItem(ADMIN_TOKEN_KEY);
    window.location.href = "/login";
  }

  return (
    <div className="cabinet-app">
      <div className="v2-console">
        <div className="console-bar">
          <div className="traffic">
            <i />
            <i />
            <i />
          </div>
          <span>admin.dlno.ru</span>
          <div className="console-avatar">A</div>
        </div>
        <div className="console-shell cabinet-shell">
          <aside>
            <Link href="/tenants" className="side-logo" aria-label="DELNO Admin">
              <DelnoMark small />
            </Link>
            {nav.map(({ href, label, Icon }) => {
              const active = pathname === href || pathname.startsWith(`${href}/`);
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
              <Link href="/tenants" className={pathname.includes("cms") ? "selected" : undefined} aria-label="CMS" title="CMS">
                <FileText />
              </Link>
              <button type="button" aria-label="Выйти" title="Выйти" onClick={logout}>
                <LogOut />
              </button>
            </div>
          </aside>
          <section className="conversation cabinet-main">{children}</section>
        </div>
      </div>
    </div>
  );
}
