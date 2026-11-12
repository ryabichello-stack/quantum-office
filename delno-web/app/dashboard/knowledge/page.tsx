"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import {
  apiInstantDemoImport,
  apiKnowledgeList,
  apiKnowledgeTemplateDownload,
  apiKnowledgeTemplates,
  apiKnowledgeUpload,
  type KnowledgeDocumentItem,
  type KnowledgeTemplateItem,
} from "@/lib/api";
import { DashboardFrame } from "@/components/DashboardFrame";
import { CabinetCard, CabinetEmpty, CabinetPage } from "@/components/CabinetPage";

function downloadTextFile(filename: string, body: string) {
  const blob = new Blob([body], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function KnowledgePage() {
  const { token } = useRequireAuth();
  const [title, setTitle] = useState("О компании");
  const [body, setBody] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [documents, setDocuments] = useState<KnowledgeDocumentItem[]>([]);
  const [templates, setTemplates] = useState<KnowledgeTemplateItem[]>([]);
  const [templateStatus, setTemplateStatus] = useState("");
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

  const loadTemplates = useCallback(async () => {
    if (!token) return;
    try {
      const result = await apiKnowledgeTemplates(token, true);
      setTemplates(result.items);
    } catch {
      /* optional */
    }
  }, [token]);

  useEffect(() => {
    void loadDocuments();
    void loadTemplates();
  }, [loadDocuments, loadTemplates]);

  async function onDownloadTemplate(id: string) {
    if (!token) return;
    setTemplateStatus("");
    try {
      const tpl = await apiKnowledgeTemplateDownload(token, id);
      downloadTextFile(tpl.filename || `${id}.md`, tpl.body);
      setTemplateStatus(`Скачан: ${tpl.title}`);
    } catch {
      setTemplateStatus("Не удалось скачать шаблон");
    }
  }

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
        <CabinetCard
          title="Шаблоны для онбординга"
          hint="Скачайте → заполните → загрузите. Или скажите Hermes голосом."
        >
          {templates.length === 0 ? (
            <CabinetEmpty
              title="Шаблоны подгрузятся с API"
              lead="Пока можно попросить Hermes: «дай шаблон профиля компании»."
            />
          ) : (
            <ul className="hx-doc-list">
              {templates.map((tpl) => (
                <li key={tpl.id}>
                  <div>
                    <strong>
                      {tpl.title}
                      {tpl.example ? " (пример)" : ""}
                    </strong>
                    <small>{tpl.description}</small>
                  </div>
                  <button type="button" className="hx-chip-link" onClick={() => void onDownloadTemplate(tpl.id)}>
                    Скачать .md
                  </button>
                </li>
              ))}
            </ul>
          )}
          {templateStatus ? <p className="hx-inline-ok">{templateStatus}</p> : null}
        </CabinetCard>

        <CabinetCard title="Документы" hint={documents.length ? `${documents.length} в базе` : "Пока пусто"}>
          {documents.length === 0 ? (
            <CabinetEmpty
              title="Знаний ещё нет"
              lead="Скачайте шаблон выше, заполните, или скажите Hermes: «дай шаблон профиля компании»."
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
