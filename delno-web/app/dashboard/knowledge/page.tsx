"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { FileText, Sparkles } from "lucide-react";
import { useRequireAuth } from "@/lib/auth";
import { apiKnowledgeList, apiKnowledgeUpload, type KnowledgeDocumentItem } from "@/lib/api";
import { DashboardFrame } from "@/components/DashboardFrame";

export default function KnowledgePage() {
  const { token } = useRequireAuth();
  const [title, setTitle] = useState("О компании");
  const [body, setBody] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [documents, setDocuments] = useState<KnowledgeDocumentItem[]>([]);

  const loadDocuments = useCallback(async () => {
    if (!token) return;
    try {
      const result = await apiKnowledgeList(token);
      setDocuments(result.items);
    } catch {
      /* list is optional UX */
    }
  }, [token]);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token || body.trim().length < 20) return;
    setError("");
    setStatus("");
    try {
      await apiKnowledgeUpload(token, title.trim(), body.trim());
      setStatus("Документ опубликован в базе знаний");
      setBody("");
      await loadDocuments();
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

      {documents.length > 0 && (
        <section className="settings-section" style={{ marginBottom: 16 }}>
          <h2>Опубликованные документы</h2>
          <ul className="kb-doc-list">
            {documents.map((doc) => (
              <li key={doc.document_id || doc.published_at || doc.title || "doc"}>
                <span>
                  <b>{doc.title || "Без названия"}</b>
                  {doc.document_id && (
                    <small style={{ display: "block", color: "#888", marginTop: 2 }}>{doc.document_id}</small>
                  )}
                </span>
                {doc.published_at && (
                  <time dateTime={doc.published_at}>
                    {new Date(doc.published_at).toLocaleDateString("ru-RU")}
                  </time>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

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
