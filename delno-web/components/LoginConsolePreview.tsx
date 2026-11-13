import { CalendarDays, Check, CircleCheck, FileText, Globe, Mail, MessageCircle, Phone, Play, Search, ShieldCheck, Sparkles, UserRound, Zap } from "lucide-react";
import { DelnoMark } from "./DelnoMark";

/** Static preview of hero console — matches landing v2 first slide */
export function LoginConsolePreview() {
  return (
    <div className="v2-console" aria-hidden="true">
      <div className="console-bar">
        <div className="traffic">
          <i />
          <i />
          <i />
        </div>
        <span>app.dlno.ru</span>
        <div className="console-avatar">Д</div>
      </div>
      <div className="console-shell" style={{ gridTemplateColumns: "55px 225px 1fr", height: 540 }}>
        <aside>
          <div className="side-logo">
            <DelnoMark small />
          </div>
          <button type="button" className="selected" aria-hidden>
            <MessageCircle />
          </button>
          <button type="button" aria-hidden>
            <UserRound />
          </button>
          <button type="button" aria-hidden>
            <CalendarDays />
          </button>
          <button type="button" aria-hidden>
            <FileText />
          </button>
          <div className="side-bottom">
            <button type="button" aria-hidden>
              <ShieldCheck />
            </button>
          </div>
        </aside>
        <section className="inbox">
          <div className="inbox-title">
            <div>
              <small>Рабочее пространство</small>
              <b>Диалоги</b>
            </div>
            <button type="button">
              <Search />
            </button>
          </div>
          <div className="inbox-filter">
            <b>
              Все <span>12</span>
            </b>
            <span>Новые 4</span>
            <span>Мои</span>
          </div>
          <article className="inbox-row hot">
            <div className="source phone">
              <Phone />
            </div>
            <div>
              <b>Анна Соколова</b>
              <p>Хочу записаться на пятницу…</p>
            </div>
            <time>сейчас</time>
          </article>
          <article className="inbox-row">
            <div className="source chat">
              <MessageCircle />
            </div>
            <div>
              <b>Михаил П.</b>
              <p>Подскажите стоимость услуги</p>
            </div>
            <time>2 мин</time>
          </article>
          <article className="inbox-row">
            <div className="source web">
              <Globe />
            </div>
            <div>
              <b>Новый посетитель</b>
              <p>Вы работаете в выходные?</p>
            </div>
            <time>5 мин</time>
          </article>
          <article className="inbox-row">
            <div className="source mail">
              <Mail />
            </div>
            <div>
              <b>ООО «Старт»</b>
              <p>Запрос коммерческого предложения</p>
            </div>
            <time>12 мин</time>
          </article>
        </section>
        <section className="conversation">
          <div className="person">
            <div>
              <b>Анна Соколова</b>
              <span>Входящий звонок · +7 921 ••• •• 18</span>
            </div>
            <div className="live-call">
              <i /> разговор завершён
            </div>
          </div>
          <div className="timeline-label">Сегодня, 12:41</div>
          <div className="voice" style={{ display: "flex", alignItems: "center", gap: 9, background: "#181916", borderRadius: 9, padding: 10, color: "#fff" }}>
            <div style={{ width: 25, height: 25, borderRadius: "50%", background: "var(--y)", color: "#111", display: "grid", placeItems: "center" }}>
              <Play style={{ width: 9, fill: "#111" }} />
            </div>
            <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 2, height: 24 }}>
              {Array.from({ length: 24 }).map((_, i) => (
                <i
                  key={i}
                  style={{
                    width: 2,
                    height: i % 5 === 0 ? 23 : i % 3 === 0 ? 18 : 7,
                    background: i % 5 === 0 ? "var(--y)" : "#e1e1dd",
                    borderRadius: 3,
                  }}
                />
              ))}
            </div>
            <span style={{ fontSize: 10, color: "#aaa" }}>2:14</span>
          </div>
          <div className="delno-result">
            <div className="result-head">
              <span>
                <Sparkles /> DELNO
              </span>
              <small>Итог разговора</small>
            </div>
            <p>Анна хочет записаться на консультацию в пятницу после 16:00. Уточнила стоимость и выбрала свободное окно.</p>
            <div className="result-tags">
              <span>Новый клиент</span>
              <span>Запись</span>
              <span>Консультация</span>
            </div>
          </div>
          <div
            className="appointment"
            style={{
              display: "grid",
              gridTemplateColumns: "34px 1fr 24px",
              gap: 9,
              alignItems: "center",
              background: "#fff5cf",
              borderRadius: 9,
              padding: 10,
              marginTop: 9,
            }}
          >
            <div className="date" style={{ background: "var(--y)", borderRadius: 7, textAlign: "center", padding: 5 }}>
              <b style={{ display: "block", fontSize: 12 }}>29</b>
              <span style={{ display: "block", fontSize: 9 }}>авг</span>
            </div>
            <div>
              <small style={{ display: "block", fontSize: 9, color: "#777" }}>Запись создана</small>
              <b style={{ display: "block", fontSize: 11, margin: "3px 0" }}>Консультация · 16:30</b>
              <span style={{ display: "block", fontSize: 9, color: "#777" }}>Анна Соколова · 60 минут</span>
            </div>
            <button type="button" style={{ width: 23, height: 23, border: 0, borderRadius: "50%", background: "#111", color: "#fff", display: "grid", placeItems: "center" }}>
              <Check style={{ width: 10 }} />
            </button>
          </div>
          <div style={{ fontSize: 10, color: "#777", display: "flex", gap: 5, alignItems: "center", marginTop: 10 }}>
            <Zap style={{ width: 11, color: "#b18400" }} /> Напоминание клиенту отправится автоматически
          </div>
          <div
            style={{
              position: "absolute",
              right: -20,
              top: 70,
              background: "#fff",
              border: "1px solid #e0e0db",
              boxShadow: "0 12px 30px #2222",
              borderRadius: 11,
              padding: "10px 12px",
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <CircleCheck style={{ width: 18, color: "#4a9859" }} />
            <div>
              <b style={{ display: "block", fontSize: 10 }}>Клиент записан</b>
              <span style={{ display: "block", fontSize: 9, color: "#888", marginTop: 2 }}>Пятница, 16:30</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
