"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { DashboardFrame } from "@/components/DashboardFrame";
import { CabinetCard, CabinetEmpty, CabinetPage } from "@/components/CabinetPage";
import { useRequireAuth } from "@/lib/auth";
import { apiAppointmentChange, apiAppointmentCreate, apiAppointmentsList, type AppointmentItem } from "@/lib/api";

const statusLabel: Record<string, string> = {
  booked: "Записан", confirmed: "Подтверждён", rescheduled: "Перенесён", cancelled: "Отменён",
};

function localTime(value: string) {
  return new Date(value).toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" });
}

export default function CalendarPage() {
  const { token } = useRequireAuth();
  const [items, setItems] = useState<AppointmentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [start, setStart] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [nextStart, setNextStart] = useState("");

  const reload = useCallback(async () => {
    if (!token) return;
    try { setItems((await apiAppointmentsList(token)).items); setError(""); }
    catch { setError("Не удалось загрузить записи. Попробуйте обновить страницу."); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => { void reload(); }, [reload]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!token || !start || !title.trim()) return;
    setBusy(true);
    try {
      await apiAppointmentCreate(token, { title: title.trim(), start: new Date(start).toISOString(), phone: phone.trim(), email: email.trim() });
      setTitle(""); setStart(""); setPhone(""); setEmail("");
      await reload();
    } catch { setError("Не удалось создать встречу. Возможно, это время уже занято."); }
    finally { setBusy(false); }
  }

  async function change(item: AppointmentItem, action: "confirm" | "cancel" | "reschedule") {
    if (!token) return;
    if (action === "cancel" && !window.confirm(`Отменить встречу «${item.title}» ${localTime(item.start)}?`)) return;
    if (action === "reschedule" && !nextStart) { setError("Укажите новую дату и время."); return; }
    setBusy(true);
    try {
      await apiAppointmentChange(token, item.id, { action, start: action === "reschedule" ? new Date(nextStart).toISOString() : undefined });
      setEditing(null); setNextStart(""); await reload();
    } catch { setError("Не удалось изменить встречу. Обновите календарь и попробуйте снова."); }
    finally { setBusy(false); }
  }

  return (
    <DashboardFrame>
      <CabinetPage kicker="Расписание" title="Календарь" lead="Встречи DELNO доступны без подключения внешнего календаря.">
        <CabinetCard title="Новая встреча">
          <form onSubmit={create} style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "end" }}>
            <label>Название<br/><input required value={title} onChange={e => setTitle(e.target.value)} placeholder="Встреча с клиентом" /></label>
            <label>Дата и время<br/><input required type="datetime-local" value={start} onChange={e => setStart(e.target.value)} /></label>
            <label>Телефон<br/><input value={phone} onChange={e => setPhone(e.target.value)} placeholder="Необязательно" /></label>
            <label>Почта<br/><input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Необязательно" /></label>
            <button type="submit" disabled={busy}>Создать</button>
          </form>
        </CabinetCard>
        <CabinetCard title={loading ? "Загрузка…" : `Встречи · ${items.length}`}>
          {error && <p className="hx-inline-error">{error}</p>}
          {!loading && items.length === 0 && <CabinetEmpty title="Встреч пока нет" lead="Создайте встречу здесь или попросите Гермеса записать клиента." />}
          {items.length > 0 && <div className="hx-table-wrap"><table className="hx-table"><thead><tr><th>Когда</th><th>Встреча</th><th>Контакт</th><th>Статус</th><th>Действия</th></tr></thead><tbody>
            {items.map(item => <tr key={item.id}>
              <td>{localTime(item.start)}</td>
              <td><strong>{item.title}</strong><small className="hx-td-sub">{item.channel}</small></td>
              <td>{item.phone || item.email || "—"}</td>
              <td>{statusLabel[item.status] || item.status}</td>
              <td>{item.status !== "cancelled" && <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {editing === item.id ? <><input aria-label="Новое время" type="datetime-local" value={nextStart} onChange={e => setNextStart(e.target.value)} /><button disabled={busy} onClick={() => void change(item, "reschedule")}>Сохранить</button><button onClick={() => setEditing(null)}>Закрыть</button></> : <button disabled={busy} onClick={() => setEditing(item.id)}>Перенести</button>}
                <button disabled={busy} onClick={() => void change(item, "confirm")}>Подтвердить</button>
                <button disabled={busy} onClick={() => void change(item, "cancel")}>Отменить</button>
              </div>}</td>
            </tr>)}
          </tbody></table></div>}
        </CabinetCard>
      </CabinetPage>
    </DashboardFrame>
  );
}
