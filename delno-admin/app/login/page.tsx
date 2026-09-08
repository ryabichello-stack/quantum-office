"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ADMIN_TOKEN_KEY, apiLogin, apiMe } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@delno.one");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const { access_token } = await apiLogin(email, password);
      const me = await apiMe(access_token);
      if (me.role !== "platform_admin") {
        setError("Нужен аккаунт platform_admin");
        return;
      }
      localStorage.setItem(ADMIN_TOKEN_KEY, access_token);
      router.push("/settings");
    } catch {
      setError("Неверный email или пароль");
    }
  }

  return (
    <main style={{ maxWidth: 420, margin: "80px auto", padding: 24 }}>
      <h1>DELNO Admin</h1>
      <p style={{ opacity: 0.7 }}>Platform admin — клиенты, CMS, секреты сервера</p>
      <form onSubmit={onSubmit} style={{ display: "grid", gap: 12, marginTop: 24 }}>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          required
          style={inputStyle}
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          required
          style={inputStyle}
        />
        {error && <p style={{ color: "#f87171" }}>{error}</p>}
        <button type="submit" style={buttonStyle}>
          Войти
        </button>
      </form>
    </main>
  );
}

const inputStyle: React.CSSProperties = {
  padding: 12,
  borderRadius: 8,
  border: "1px solid #334155",
  background: "#111827",
  color: "#fff",
};
const buttonStyle: React.CSSProperties = {
  padding: 12,
  borderRadius: 8,
  border: "none",
  background: "#2563eb",
  color: "#fff",
  cursor: "pointer",
};
