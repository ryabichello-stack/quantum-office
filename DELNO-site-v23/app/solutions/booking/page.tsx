import Link from "next/link";
import { LossCalculator } from "@/components/booking/LossCalculator";
import { buildDelnoMetadata } from "@/lib/buildMetadata";
import { V17PageShell } from "@/app/v2/v17/V17PageShell";

import "../../v2/dv17.bundle.css";
import "../../v2/v17-overrides.css";
import "./solution.css";

export const metadata = buildDelnoMetadata({
  title: "Запись клиентов без потерянных обращений — DELNO",
  description: "Как принимать обращения, уточнять услугу и время, передавать заявку на запись и подтверждать результат клиенту. Посчитайте стоимость пропущенных обращений.",
  path: "/solutions/booking",
});

const steps = [
  ["01", "Ответить", "Клиент задаёт вопрос на сайте или в подключённом канале. DELNO отвечает по согласованным услугам, ценам и правилам."],
  ["02", "Уточнить", "Собирает только необходимые детали: услугу, удобное время и контакт. Длинная анкета в начале разговора не нужна."],
  ["03", "Передать к записи", "Передаёт структурированную заявку ответственному. Создание записи в календаре зависит от подключённой системы и правил подтверждения."],
  ["04", "Сообщить статус", "Клиенту должно быть ясно, запись уже подтверждена или заявка ещё ожидает ответа администратора."],
];

export default function BookingSolutionPage() {
  return (
    <V17PageShell>
      <div className="dc-content-page dc-solution-page">
        <div className="dc-content-wrap dc-solution-wrap">
          <Link href="/" className="dv17-inline-link">← На главную</Link>
          <p className="dv17-eyebrow">Одна задача для первого запуска</p>
          <h1>Запись начинается с ответа клиенту</h1>
          <p className="dc-solution-lead">Когда администратор занят, клиенту важно быстро получить ответ и понятный следующий шаг. DELNO помогает обработать обращение и передать данные для записи без лишних вопросов.</p>
          <div className="dc-solution-actions">
            <Link href="/#contact" className="dv17-button dv17-primary">Обсудить свой сценарий</Link>
          </div>
          <section className="dc-solution-section" aria-labelledby="booking-flow-title">
            <p className="dv17-eyebrow">Как устроен сценарий</p>
            <h2 id="booking-flow-title">От вопроса до понятного результата</h2>
            <ol className="dc-solution-steps">
              {steps.map(([number, title, description]) => <li key={number}><span>{number}</span><div><h3>{title}</h3><p>{description}</p></div></li>)}
            </ol>
          </section>
          <section className="dc-solution-section" aria-labelledby="booking-check-title">
            <p className="dv17-eyebrow">Перед подключением</p>
            <h2 id="booking-check-title">Что нужно проверить вместе</h2>
            <div className="dc-solution-columns">
              <div><h3>Материалы бизнеса</h3><p>Услуги, длительность, цены, график, правила переноса и вопросы, которые должен решать человек.</p></div>
              <div><h3>Куда попадает заявка</h3><p>Почта, таблица, кабинет или система записи. Связку с конкретным календарём проверяем до обещания автоматической брони.</p></div>
              <div><h3>Что видит клиент</h3><p>Разделяем статусы «заявка отправлена» и «время подтверждено». Это защищает от ошибок и двойной записи.</p></div>
            </div>
          </section>
          <LossCalculator />
          <section className="dc-solution-section dc-solution-reading" aria-labelledby="booking-reading-title">
            <h2 id="booking-reading-title">Разобраться подробнее</h2>
            <ul>
              <li><Link href="/blog/prepare-knowledge-base">Что подготовить для первого сценария</Link></li>
              <li><Link href="/blog/launch-checklist">Как проверить сценарий перед запуском</Link></li>
              <li><Link href="/blog/one-employee-many-channels">Один сотрудник для нескольких каналов</Link></li>
              <li><Link href="/blog/online-booking-clients-guide">Как выбрать систему онлайн-записи</Link></li>
            </ul>
          </section>
        </div>
      </div>
    </V17PageShell>
  );
}
