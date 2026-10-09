import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { V17PageShell } from "../v17/V17PageShell";

export default function V2HelpPage() {
  return (
    <V17PageShell>
      <div className="dc-content-page">
        <div className="dc-content-wrap">
          <Link href="/v2" className="dv17-inline-link">
            <ArrowLeft size={16} aria-hidden /> На главную V17
          </Link>
          <h1>Как пользоваться DELNO</h1>
          <ol>
            <li>Попробуйте голосовое демо на главной — задайте вопрос о тарифах или подключении.</li>
            <li>Оставьте заявку — подберём одну задачу для первого сценария.</li>
            <li>Передайте сайт, прайс и правила — настроим базу знаний и канал.</li>
            <li>Вместе проверим диалоги и запустим на вашем бизнесе.</li>
          </ol>
          <p>
            Вопросы: <a href="mailto:office@dlno.ru">office@dlno.ru</a> ·{" "}
            <a href="https://t.me/Dlno_bot">Telegram</a>
          </p>
        </div>
      </div>
    </V17PageShell>
  );
}
