"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { FileText, Sparkles } from "lucide-react";
import { useRequireAuth } from "@/lib/auth";
import { apiKnowledgeUpload } from "@/lib/api";
import { DashboardFrame } from "@/components/DashboardFrame";

export default function KnowledgePage() {
  const { token } = useRequireAuth();
  const [title, setTitle] = useState("О компании");
  const [body, setBody] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || body.trim().length < 20) return;
    setError("");
    setStatus("");
    try {
      await apiKnowledgeUpload(token, title.trim(), body.trim());
      setStatus("Документ отправлен в базу знаний");
      setBody("");
    } catch {
      setError("Не удалось загрузить документ");
    }
  }

  return (
    <DashboardFrame>
      <div className="page-head">
        <small>DELNO Кабинет</small>
        <h1>Знания</h1>
        <p>Текст попадает в brain и используется во всех каналах.</p>
      </div>

      <div className="delno-result" style={{ marginBottom: 16 }}>
        <div className="result-head">
          <span>
            <Sparkles /> Operator
          </span>
        </div>
        <p style={{ margin: 0 }}>
          Быстрее на лету:{" "}
          <Link href="/dashboard/operator" style={{ fontWeight: 700 }}>
            «Добавь в базу знаний: …»
          </Link>
        </p>
      </div>

      <form className="settings-section kb-upload-form" onSubmit={onSubmit}>
        <h2>
          <FileText style={{ width: 16, height: 16, verticalAlign: -2, marginRight: 6 }} />
          Добавить текст
        </h2>
        <label>
          Заголовок
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label>
          Содержание
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={8}
            placeholder="Услуги, цены, часы работы, правила общения…"
          />
        </label>
        <button type="submit" className="btn-primary" disabled={!token || body.trim().length < 20}>
          Опубликовать в KB
        </button>
        {status && <p className="login-status">{status}</p>}
        {error && <p className="status-error">{error}</p>}
      </form>
    </DashboardFrame>
  );
}
