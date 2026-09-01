"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiLogin } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("owner@delno.one");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const { access_token } = await apiLogin(email, password);
      localStorage.setItem("delno_token", access_token);
      router.push("/dashboard");
    } catch {
      setError("Неверный email или пароль");
    }
  }

  return (
    <main style={{ maxWidth: 420, margin: "80px auto", padding: 24 }}>
      <h1 style={{ margin: 0, fontSize: 32, letterSpacing: "-0.03em" }}>DELNO</h1>
      <p style={{ color: "#64748b" }}>Личный кабинет — заявки, диалоги, Operator</p>
      <form onSubmit={onSubmit} style={{ display: "grid", gap: 12, marginTop: 24 }}>
        <label style={{ display: "grid", gap: 6, fontSize: 13 }}>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required style={inputStyle} />
        </label>
        <label style={{ display: "grid", gap: 6, fontSize: 13 }}>
          Пароль
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            style={inputStyle}
          />
        </label>
        {error && <p style={{ color: "#dc2626" }}>{error}</p>}
        <button type="submit" style={buttonStyle}>Войти</button>
      </form>
    </main>
  );
}

const inputStyle: React.CSSProperties = { padding: 12, borderRadius: 8, border: "1px solid #cbd5e1" };
const buttonStyle: React.CSSProperties = { padding: 12, borderRadius: 8, border: "none", background: "#0f172a", color: "#fff" };
