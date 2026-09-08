"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ADMIN_TOKEN_KEY } from "@/lib/api";

export function AdminShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  function logout() {
    localStorage.removeItem(ADMIN_TOKEN_KEY);
    window.location.href = "/login";
  }

  const link = (href: string, label: string) => {
    const active = pathname === href || pathname.startsWith(`${href}/`);
    return (
      <Link
        href={href}
        style={{
          color: active ? "#fff" : "#93c5fd",
          textDecoration: active ? "underline" : "none",
          fontWeight: active ? 600 : 400,
        }}
      >
        {label}
      </Link>
    );
  };

  return (
    <main style={{ maxWidth: 960, margin: "40px auto", padding: 24 }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
        <div>
          <p style={{ margin: 0, opacity: 0.6, fontSize: 13 }}>DELNO Platform</p>
          <h1 style={{ margin: "4px 0 0" }}>{title}</h1>
        </div>
        <nav style={{ display: "flex", gap: 16, alignItems: "center", fontSize: 14 }}>
          {link("/tenants", "Клиенты")}
          {link("/settings", "Секреты")}
          <button type="button" onClick={logout} style={ghostBtn}>
            Выйти
          </button>
        </nav>
      </header>
      <div style={{ marginTop: 32 }}>{children}</div>
    </main>
  );
}

const ghostBtn: React.CSSProperties = {
  padding: "8px 12px",
  borderRadius: 8,
  border: "1px solid #334155",
  background: "transparent",
  color: "#93c5fd",
  cursor: "pointer",
};
