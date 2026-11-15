import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { mainPath } from "@/lib/landingPaths";
import { V17PageShell } from "../v2/v17/V17PageShell";
import { buildDelnoMetadata } from "@/lib/buildMetadata";

import "../v2/dv17.bundle.css";
import "../v2/v17-overrides.css";

export const metadata = buildDelnoMetadata({
  title: "С чего начать с DELNO",
  description: "Выберите задачу, оцените поток обращений и оставьте заявку. Что подготовить к первому разговору с DELNO.",
  path: "/help",
});

export default function HelpPage() {
  return (
    <V17PageShell>
      <div className="dc-content-page">
        <div className="dc-content-wrap">
          <Link href={mainPath("/")} className="dv17-inline-link">
            <ArrowLeft size={16} aria-hidden /> На главную
          </Link>
          <h1>С чего начать с DELNO</h1>
          <ol>
            <li>Выберите одну задачу: пропущенные обращения, заявки на запись или работа после закрытия.</li>
            <li>Посчитайте недельный поток: сколько запросов пришло, сколько получили ответ и чем закончились.</li>
            <li>Оставьте заявку — уточним вашу задачу и желаемый результат.</li>
            <li>Если сценарий подходит, отдельно согласуем сроки, объём и стоимость.</li>
          </ol>
          <section aria-labelledby="check-delno-title">
            <h2 id="check-delno-title">Как проверить работу DELNO</h2>
            <p>
              Задайте вопрос плавающему помощнику на этом сайте или напишите в{" "}
              <a href="https://t.me/Dlno_bot" target="_blank" rel="noreferrer">Telegram</a> и{" "}
              <a href="https://max.ru/id471405233378_bot" target="_blank" rel="noreferrer">MAX</a>.
              Так можно проверить ответы по сведениям о сервисе в открытых каналах.
            </p>
            <p>
              Телефония, календарь и CRM связаны с данными конкретной компании. Если вам нужно оценить
              такой сценарий, опишите задачу в заявке — согласуем безопасный способ проверки.
            </p>
          </section>
          <p>
            Вопросы: <a href="mailto:office@dlno.ru">office@dlno.ru</a> ·{" "}
            <a href="https://t.me/Dlno_bot">Telegram</a>
          </p>
        </div>
      </div>
    </V17PageShell>
  );
}
