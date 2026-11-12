"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import {
  apiInstantDemoImport,
  apiKnowledgeList,
  apiKnowledgeUpload,
  type KnowledgeDocumentItem,
} from "@/lib/api";
import { DashboardFrame } from "@/components/DashboardFrame";
import { CabinetCard, CabinetEmpty, CabinetPage } from "@/components/CabinetPage";

export default function KnowledgePage() {
  const { token } = useRequireAuth();
  const [title, setTitle] = useState("О компании");
  const [body, setBody] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [documents, setDocuments] = useState<KnowledgeDocumentItem[]>([]);
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [importStatus, setImportStatus] = useState("");
  const [importError, setImportError] = useState("");
  const [widgetEmbed, setWidgetEmbed] = useState("");

  const loadDocuments = useCallback(async () => {
    if (!token) return;
    try {
      const result = await apiKnowledgeList(token);
      setDocuments(result.items);
    } catch {
      /* optional */
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
      setStatus("Документ опубликован");
      setBody("");
      await loadDocuments();
    } catch {
      setError("Не удалось загрузить документ");
    }
  }

  async function onImportWebsite(e: FormEvent) {
    e.preventDefault();
    if (!token || websiteUrl.trim().length < 4) return;
    setImportError("");
    setImportStatus("");
    setWidgetEmbed("");
    try {
      const result = await apiInstantDemoImport(token, websiteUrl.trim());
      setImportStatus(`Импортировано: ${result.title}`);
      setWidgetEmbed(result.widget_embed);
      setTitle(result.title);
      await loadDocuments();
    } catch {
      setImportError("Не удалось импортировать сайт");
    }
  }

  return (
    <DashboardFrame>
      <CabinetPage
        kicker="База"
        title="Знания"
        lead="То, по чему Hermes и каналы отвечают клиентам."
        actions={
          <Link href="/dashboard/hermes" className="hx-chip-link">
            Попросить Hermes собрать с сайта
          </Link>
        }
      >
        <CabinetCard title="Документы" hint={documents.length ? `${documents.length} в базе` : "Пока пусто"}>
          {documents.length === 0 ? (
            <CabinetEmpty
              title="Знаний ещё нет"
              lead="Добавьте текст ниже или скажите Hermes: «зайди на мой сайт»."
            />
          ) : (
            <ul className="hx-doc-list">
              {documents.map((doc) => (
                <li key={doc.document_id || doc.published_at || doc.title || "doc"}>
                  <div>
                    <strong>{doc.title || "Без названия"}</strong>
                    {doc.document_id ? <small>{doc.document_id}</small> : null}
                  </div>
                  {doc.published_at ? (
                    <time dateTime={doc.published_at}>
                      {new Date(doc.published_at).toLocaleDateString("ru-RU", { timeZone: "Europe/Moscow" })}
                    </time>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CabinetCard>

        <CabinetCard title="Добавить текст" hint="Минимум 20 символов">
          <form className="hx-form" onSubmit={onSubmit}>
            <label>
              Заголовок
              <input value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label>
              Содержание
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={7}
                placeholder="Услуги, цены, часы работы, правила…"
              />
            </label>
            <button type="submit" className="hx-primary-btn" disabled={!token || body.trim().length < 20}>
              Опубликовать
            </button>
            {status ? <p className="hx-inline-ok">{status}</p> : null}
            {error ? <p className="hx-inline-error">{error}</p> : null}
          </form>
        </CabinetCard>

        <CabinetCard title="Импорт с сайта" hint="Быстрый legacy-путь. Удобнее через Hermes.">
          <form className="hx-form" onSubmit={onImportWebsite}>
            <label>
              URL
              <input
                value={websiteUrl}
                onChange={(e) => setWebsiteUrl(e.target.value)}
                placeholder="https://ваша-компания.ru"
                type="url"
              />
            </label>
            <button type="submit" className="hx-primary-btn" disabled={!token || websiteUrl.trim().length < 4}>
              Импортировать
            </button>
            {importStatus ? <p className="hx-inline-ok">{importStatus}</p> : null}
            {importError ? <p className="hx-inline-error">{importError}</p> : null}
            {widgetEmbed ? (
              <label>
                Код виджета
                <textarea readOnly rows={3} value={widgetEmbed} />
              </label>
            ) : null}
          </form>
        </CabinetCard>
      </CabinetPage>
    </DashboardFrame>
  );
}
