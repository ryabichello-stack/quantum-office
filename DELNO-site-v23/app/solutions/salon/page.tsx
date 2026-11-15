import Link from "next/link";
import { LeadFormTrigger } from "@/app/v2/SiteControls";
import { V17PageShell } from "@/app/v2/v17/V17PageShell";
import { buildDelnoMetadata } from "@/lib/buildMetadata";

import "../../v2/dv17.bundle.css";
import "../../v2/v17-overrides.css";
import "../booking/solution.css";

export const metadata = buildDelnoMetadata({
  title: "Заявки на запись в салон красоты: как не терять клиентов — DELNO",
  description: "Как салону отвечать на обращения, отличать запрос от подтверждённой записи и оценить потери от пустых окон. Оцените задачу для DELNO.",
  path: "/solutions/salon",
});

export default function SalonSolutionPage() {
  return (
    <V17PageShell>
      <div className="dc-content-page dc-solution-page">
        <div className="dc-content-wrap dc-solution-wrap">
          <Link href="/" className="dv17-inline-link">← На главную</Link>
          <p className="dv17-eyebrow">Для салонов красоты и мастеров</p>
          <h1>Клиент написал о записи. Что будет дальше?</h1>
          <p className="dc-solution-lead">Салон получает запросы между процедурами, после закрытия и в нескольких каналах. Важно быстро ответить, уточнить услугу и передать запрос так, чтобы клиент не принял заявку за подтверждённое время.</p>
          <div className="dc-solution-actions">
            <LeadFormTrigger className="dv17-button dv17-primary" label="Оставить заявку" source="solution salon" />
            <Link href="/solutions/booking" className="dv17-button dv17-secondary">Посчитать возможные потери</Link>
          </div>

          <section className="dc-solution-section">
            <h2>Три места, где запись теряется</h2>
            <div className="dc-solution-columns">
              <div><h3>Во время процедуры</h3><p>Мастер не может отвечать сразу. Клиент спрашивает цену и ближайшее время, затем пишет другому салону.</p></div>
              <div><h3>После закрытия</h3><p>Сообщение остаётся до утра. Полезный первый ответ должен назвать условия и срок ответа, не выдумывая свободный слот.</p></div>
              <div><h3>При переносе</h3><p>Старое время освобождается, но об этом не узнают другие клиенты. Важно зафиксировать новый статус и передать его администратору.</p></div>
            </div>
          </section>

          <section className="dc-solution-section">
            <h2>Какой сценарий стоит проверять первым</h2>
            <ol className="dc-solution-steps">
              <li><span>01</span><h3>Собрать запрос</h3><p>Услуга, желаемый день, удобный способ связи. Длинная анкета на первом шаге не нужна.</p></li>
              <li><span>02</span><h3>Дать проверенный ответ</h3><p>Цена или диапазон, длительность и правила из актуальных материалов салона.</p></li>
              <li><span>03</span><h3>Передать ответственному</h3><p>Заявка с контекстом попадает человеку, который видит расписание и подтверждает время.</p></li>
              <li><span>04</span><h3>Измерить результат</h3><p>Сколько обращений дошло до ответа, заявки и подтверждённого визита — это разные числа.</p></li>
            </ol>
          </section>

          <section className="dc-solution-section">
            <h2>Что нужно для расчёта</h2>
            <p>Возьмите за неделю число обращений по каналам, время первого ответа, число заявок и подтверждённых визитов. Добавьте среднюю маржу визита и число незаполненных окон. Эти данные помогут оценить экономику вашего сценария; средние проценты из чужих кейсов здесь не заменяют ваши цифры.</p>
            <p>Сейчас мы собираем заявки и проверяем спрос. Подключение к конкретной системе записи и автоматическое подтверждение времени обсуждаем отдельно после проверки процесса.</p>
          </section>

          <section className="dc-solution-section dc-solution-reading">
            <h2>Полезно перед разговором</h2>
            <ul>
              <li><Link href="/blog/lost-leads-messengers">Как посчитать потерянные обращения</Link></li>
              <li><Link href="/blog/no-show-cost">Как оценить стоимость пустых окон</Link></li>
              <li><Link href="/blog/booking-any-service">Как различать заявку и запись</Link></li>
              <li><Link href="/blog/online-booking-clients-guide">Как выбрать систему онлайн-записи</Link></li>
            </ul>
            <LeadFormTrigger className="dv17-button dv17-primary" label="Обсудить свою задачу" source="solution salon bottom" />
          </section>
        </div>
      </div>
    </V17PageShell>
  );
}
