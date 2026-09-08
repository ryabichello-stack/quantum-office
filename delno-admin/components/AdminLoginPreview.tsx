import { Building2, FileText, KeyRound, ShieldCheck } from "lucide-react";
import { DelnoMark } from "./DelnoMark";

export function AdminLoginPreview() {
  return (
    <div className="v2-console" aria-hidden="true">
      <div className="console-bar">
        <div className="traffic">
          <i />
          <i />
          <i />
        </div>
        <span>admin.dlno.ru</span>
        <div className="console-avatar">A</div>
      </div>
      <div className="console-shell" style={{ gridTemplateColumns: "55px 225px 1fr", height: 540 }}>
        <aside>
          <div className="side-logo">
            <DelnoMark small />
          </div>
          <button type="button" className="selected" aria-hidden>
            <Building2 />
          </button>
          <button type="button" aria-hidden>
            <FileText />
          </button>
          <button type="button" aria-hidden>
            <KeyRound />
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
              <small>Platform</small>
              <b>Клиенты</b>
            </div>
          </div>
          <article className="inbox-row hot">
            <div className="source web">
              <Building2 />
            </div>
            <div>
              <b>delno-demo</b>
              <p>DELNO Demo</p>
            </div>
            <time>live</time>
          </article>
          <article className="inbox-row">
            <div className="source chat">
              <FileText />
            </div>
            <div>
              <b>CMS faq</b>
              <p>published</p>
            </div>
            <time>ru</time>
          </article>
        </section>
        <section className="conversation">
          <div className="page-head">
            <small>Platform admin</small>
            <h1>Секреты сервера</h1>
            <p>OpenAI, JWT, Telegram — в /opt/delno/.env</p>
          </div>
          <div className="panel-card">
            <b style={{ fontSize: 12 }}>OPENAI_API_KEY</b>
            <p style={{ margin: "8px 0 0", fontSize: 13, color: "#666" }}>••••••••abcd · cedar · Realtime</p>
          </div>
        </section>
      </div>
    </div>
  );
}
