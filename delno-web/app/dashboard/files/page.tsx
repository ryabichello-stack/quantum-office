"use client";

import { useCallback, useEffect, useState } from "react";
import { DashboardFrame } from "@/components/DashboardFrame";
import { CabinetCard, CabinetEmpty, CabinetPage } from "@/components/CabinetPage";
import { useRequireAuth } from "@/lib/auth";
import { apiTenantFileUpload, apiTenantFilesList, apiTenantFolderCreate, apiTenantFolderDelete, apiTenantFileDelete, apiTenantFileMove, apiTenantFileDownload, type TenantFileItem, type TenantFolderItem } from "@/lib/api";

function fileSize(bytes: number) {
  return bytes < 1024 ? `${bytes} Б` : `${(bytes / 1024 / 1024).toFixed(2)} МБ`;
}

export default function FilesPage() {
  const { token } = useRequireAuth();
  const [files, setFiles] = useState<TenantFileItem[]>([]);
  const [folders, setFolders] = useState<TenantFolderItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [currentFolder, setCurrentFolder] = useState<string | null>(null);
  const [folderName, setFolderName] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const reload = useCallback(async () => {
    if (!token) return;
    try { const result = await apiTenantFilesList(token); setFiles(result.items); setFolders(result.folders); setHasMore(result.items.length === 500); }
    catch { setMessage("Не удалось загрузить список файлов."); }
  }, [token]);

  useEffect(() => { void reload(); }, [reload]);

  const activeFolder = folders.find(folder => folder.id === currentFolder);
  const visibleFolders = folders.filter(folder => folder.parent_id === currentFolder);
  const visibleFiles = files.filter(file => file.folder_id === currentFolder);

  async function action(work: () => Promise<unknown>, error: string) {
    setBusy(true); setMessage("");
    try { await work(); await reload(); }
    catch { setMessage(error); }
    finally { setBusy(false); }
  }

  return <DashboardFrame><CabinetPage kicker="Рабочее пространство" title="Файлы" lead="Документы, таблицы и презентации вашей компании.">
    <CabinetCard title="Загрузить файл" hint="Гермес сможет приложить выбранный файл к письму по вашему поручению.">
      <p>Папка: {activeFolder?.name || "Главная"}</p>
      <input type="file" aria-label="Загрузить файл компании" disabled={busy} onChange={async event => {
        const file = event.target.files?.[0];
        if (!file || !token) return;
        setBusy(true); setMessage("Загружаю…");
        try { await apiTenantFileUpload(token, file, currentFolder); await reload(); setMessage("Файл сохранён для вашей компании."); }
        catch { setMessage("Не удалось сохранить файл. Максимальный размер — 10 МБ."); }
        finally { setBusy(false); event.target.value = ""; }
      }} />
      {message && <p role="status">{message}</p>}
    </CabinetCard>
    <CabinetCard title={activeFolder?.name || "Главная папка"}>
      {currentFolder && <button type="button" disabled={busy} onClick={() => setCurrentFolder(activeFolder?.parent_id || null)}>← Назад</button>}
      <form onSubmit={event => { event.preventDefault(); if (token && folderName.trim()) void action(async () => { await apiTenantFolderCreate(token, folderName.trim(), currentFolder); setFolderName(""); }, "Не удалось создать папку. Проверьте название."); }} style={{display: "flex", gap: 8, marginTop: 12}}>
        <input aria-label="Название новой папки" placeholder="Новая папка" value={folderName} onChange={event => setFolderName(event.target.value)} maxLength={120} />
        <button type="submit" disabled={busy || !folderName.trim()}>Создать папку</button>
      </form>
      {activeFolder && <p><button type="button" disabled={busy} onClick={() => { if (token && window.confirm(`Удалить пустую папку «${activeFolder.name}»?`)) void action(async () => { await apiTenantFolderDelete(token, activeFolder.id); setCurrentFolder(activeFolder.parent_id); }, "Удалить можно только пустую папку."); }}>Удалить эту папку</button></p>}
      {visibleFolders.length > 0 && <ul>{visibleFolders.map(folder => <li key={folder.id}><button type="button" onClick={() => setCurrentFolder(folder.id)}>📁 {folder.name}</button></li>)}</ul>}
      {visibleFiles.length === 0 && visibleFolders.length === 0 ? <CabinetEmpty title="Здесь пока пусто" lead="Создайте папку или загрузите файл." /> :
        visibleFiles.length > 0 && <div className="hx-table-wrap"><table className="hx-table"><thead><tr><th>Название</th><th>Размер</th><th>Действия</th></tr></thead><tbody>
          {visibleFiles.map(file => <tr key={file.id}><td>{file.name}</td><td>{fileSize(file.bytes)}</td><td>
            <button type="button" disabled={busy} onClick={() => { if (token) void action(() => apiTenantFileDownload(token, file), "Не удалось скачать файл."); }}>Скачать</button>{" "}
            <select aria-label={`Переместить ${file.name}`} disabled={busy} value={file.folder_id || ""} onChange={event => { if (token) void action(() => apiTenantFileMove(token, file.id, event.target.value || null), "Не удалось переместить файл."); }}>
              <option value="">Главная</option>{folders.map(folder => <option key={folder.id} value={folder.id}>{folder.name}</option>)}
            </select>{" "}
            <button type="button" disabled={busy} onClick={() => { if (token && window.confirm(`Удалить файл «${file.name}»?`)) void action(() => apiTenantFileDelete(token, file.id), "Не удалось удалить файл."); }}>Удалить</button>
          </td></tr>)}
        </tbody></table></div>}
      {hasMore && <p><button type="button" disabled={busy} onClick={() => { if (!token) return; setBusy(true); void apiTenantFilesList(token, files.length).then(result => { setFiles(current => [...current, ...result.items]); setHasMore(result.items.length === 500); }).catch(() => setMessage("Не удалось загрузить следующую страницу файлов.")).finally(() => setBusy(false)); }}>Показать ещё файлы</button></p>}
    </CabinetCard>
  </CabinetPage></DashboardFrame>;
}
