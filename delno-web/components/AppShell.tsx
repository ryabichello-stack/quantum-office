"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/auth";
import type { TenantMe } from "@/lib/api";
import { colors } from "@/lib/ui";

const nav = [
  { href: "/dashboard", label: "Обзор" },
  { href: "/dashboard/leads", label: "Заявки" },
  { href: "/dashboard/inbox", label: "Диалоги" },
  { href: "/dashboard/operator", label: "Operator" },
  { href: "/dashboard/settings", label: "Настройки" },
];

export function AppShell({ me, children }: { me: TenantMe | null; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: colors.bg }}>
      <aside
        style={{
          width: 240,
          background: colors.accent,
          color: "#fff",
          padding: "24px 16px",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        <div style={{ padding: "0 8px 24px" }}>
          <div style={{ fontWeight: 800, fontSize: 20, letterSpacing: "-0.03em" }}>DELNO</div>
          <div style={{ fontSize: 12, opacity: 0.7, marginTop: 4 }}>Личный кабинет</div>
        </div>
        {nav.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              style={{
                display: "block",
                padding: "10px 12px",
                borderRadius: 8,
                textDecoration: "none",
                color: "#fff",
                background: active ? "rgba(255,255,255,0.12)" : "transparent",
                fontWeight: active ? 700 : 500,
              }}
            >
              {item.label}
            </Link>
          );
        })}
        <div style={{ marginTop: "auto", padding: 8, fontSize: 12, opacity: 0.75 }}>
          {me?.tenant_slug}
          <br />
          {me?.role}
        </div>
        <button
          type="button"
          onClick={() => {
            clearToken();
            router.push("/");
          }}
          style={{
            marginTop: 8,
            padding: "8px 12px",
            borderRadius: 8,
            border: "1px solid rgba(255,255,255,0.2)",
            background: "transparent",
            color: "#fff",
            cursor: "pointer",
          }}
        >
          Выйти
        </button>
      </aside>
      <main style={{ flex: 1, padding: "32px 28px", maxWidth: 1100 }}>{children}</main>
    </div>
  );
}
