import { ArrowDown, CalendarDays, Check, MessageCircle, Mic, Phone, Sparkles, UserRound } from "lucide-react";
import Link from "next/link";
import "./v2.css";
import "./mobile.css";
import { DelnoMark } from "./DelnoPage";
import { FaqSection, type FaqItem } from "./FaqSection";
import VoiceDemo from "./VoiceDemo";
import { LeadFormTrigger } from "./SiteControls";
import { ConvertPricingNote, StickyMobileCTA } from "./SiteConvert";

const hireFaq: FaqItem[] = [
  [
    "Это замена администратору?",
    "DELNO закрывает повторяющуюся первую линию: ответы, запись, приём контактов. Сложные и медицинские решения остаются за человеком — с готовым контекстом диалога.",
  ],
  [
    "Что входит в 2 990 ₽?",
    "Сайт и мессенджеры, база знаний, до 300 ИИ-диалогов и 30 минут голоса в виджете. Обычные телефонные звонки (PSTN) — в тарифе 5 990 ₽.",
  ],
  [
    "Можно услышать голос до подключения?",
    "Да — на этой странице. Нажмите на кристалл и задайте вопрос вслух, как ваш клиент.",
  ],
  [
    "DELNO придумает ответ, если не знает?",
    "Нет. Уточнит вопрос или передаст обращение человеку вместе с уже собранным контекстом.",
  ],
];

const pillars = [
  {
    icon: MessageCircle,
    title: "Отвечает",
    text: "На сайте, в Telegram и MAX — из одной базы знаний, без «бота на каждый канал».",
  },
  {
    icon: CalendarDays,
    title: "Записывает",
    text: "Уточняет услугу и время, создаёт запись и отправляет подтверждение клиенту.",
  },
  {
    icon: UserRound,
    title: "Передаёт человеку",
    text: "Когда вопрос выходит за рамки — не выдумывает, а передаёт диалог с контекстом.",
  },
];

export default function ConvertLanding() {
  return (
    <main className="v2 v2-convert v2-hire-page">
      <header className="v2-header hire-header">
        <Link className="v2-logo hire-logo" href="/v2">
          <DelnoMark />
          DELNO
        </Link>
        <Link className="hire-main-link" href="/">
          Основной сайт
        </Link>
        <div className="v2-header-right">
          <a className="hire-scroll-cta" href="#demo">
            <Mic aria-hidden />
            Спросить вслух
          </a>
          <LeadFormTrigger className="v2-btn compact hire-lead-header" label="Нанять DELNO" source="Header v2-hire" />
        </div>
      </header>

      <section className="hire-hero" id="top">
        <div className="hire-hero-glow" aria-hidden />
        <div className="hire-hero-inner">
          <p className="hire-eyebrow">
            <Sparkles aria-hidden />
            ИИ-сотрудник на первой линии
          </p>
          <h1>
            Ваш следующий сотрудник —
            <span> не человек.</span>
          </h1>
          <p className="hire-lead">
            DELNO принимает обращения на сайте, в мессенджерах и по телефону (по тарифу). Отвечает по вашим
            правилам, записывает клиентов и работает, когда смена уже закончилась.
          </p>
          <div className="hire-hero-actions">
            <LeadFormTrigger className="v2-btn primary hire-btn-primary" label="Нанять DELNO" source="Hero v2-hire" />
            <a className="v2-btn secondary hire-btn-secondary" href="#demo">
              Сначала — голос за 30 сек
            </a>
          </div>
          <ul className="hire-stats" aria-label="Ключевые цифры">
            <li>
              <strong>300</strong>
              <span>диалогов в пакете</span>
            </li>
            <li>
              <strong>24/7</strong>
              <span>на подключённых каналах</span>
            </li>
            <li>
              <strong>от 2 990 ₽</strong>
              <span>без карты на старте</span>
            </li>
          </ul>
        </div>
        <a className="hire-scroll-hint" href="#demo">
          <span>Живое демо</span>
          <ArrowDown aria-hidden />
        </a>
      </section>

      <VoiceDemo embed />

      <section className="hire-pillars v2-section" id="why">
        <div className="v2-kicker pale">Зачем нанимать DELNO</div>
        <h2 className="hire-h2">
          Одна роль вместо
          <span> пяти разрозненных сервисов.</span>
        </h2>
        <div className="hire-pillar-grid">
          {pillars.map(({ icon: Icon, title, text }) => (
            <article key={title}>
              <div className="hire-pillar-icon">
                <Icon aria-hidden />
              </div>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="hire-proof">
        <p>
          «Вы работаете в субботу?» · «Сколько стоит?» · «Можно завтра вечером?» — DELNO отвечает из вашей базы
          знаний и ведёт к записи или заявке.
        </p>
        <div className="hire-proof-channels">
          <span>Сайт</span>
          <span>Telegram</span>
          <span>MAX</span>
          <span>Телефон</span>
          <span>Почта</span>
        </div>
      </section>

      <section className="v2-pricing hire-pricing" id="prices">
        <div className="v2-pricing-head">
          <div className="v2-kicker pale">Тарифы</div>
          <h2>Выберите, как к вам обращаются клиенты</h2>
          <p>Лимиты в открытом доступе — без «уточним по телефону».</p>
        </div>
        <ConvertPricingNote />
        <div className="v2-price-grid hire-price-grid">
          <article>
            <span>Диалоги</span>
            <h3>
              2 990 ₽<small>/ мес.</small>
            </h3>
            <p>Сайт, мессенджеры, голос в виджете — без PSTN.</p>
            <ul>
              <li>
                <Check aria-hidden /> 300 ИИ-диалогов
              </li>
              <li>
                <Check aria-hidden /> 30 мин голоса на сайте
              </li>
              <li>
                <Check aria-hidden /> Единая база знаний
              </li>
            </ul>
            <LeadFormTrigger className="price-lead" label="Начать с чатов" source="Hire 2990" />
          </article>
          <article className="best">
            <div className="best-label">Если звонят</div>
            <span>Диалоги + звонки</span>
            <h3>
              5 990 ₽<small>/ мес.</small>
            </h3>
            <p>Всё из «Диалоги» + телефония.</p>
            <ul>
              <li>
                <Check aria-hidden /> 100 мин PSTN
              </li>
              <li>
                <Check aria-hidden /> Входящие и исходящие
              </li>
              <li>
                <Check aria-hidden /> Итог звонка человеку
              </li>
            </ul>
            <LeadFormTrigger className="price-lead" label="Нанять с телефоном" source="Hire 5990" />
          </article>
        </div>
      </section>

      <FaqSection fallback={hireFaq} version4 />

      <section className="v2-final hire-final" id="contact">
        <div className="final-glow" />
        <h2>
          Нанять DELNO
          <span> проще, чем искать ещё одного администратора.</span>
        </h2>
        <p>Сначала голос на этой странице — затем демо на материалах вашего бизнеса.</p>
        <div className="hire-final-actions">
          <LeadFormTrigger className="v2-btn primary" label="Получить демо" source="Финал v2-hire" />
          <a className="v2-btn secondary" href="#demo">
            <Mic aria-hidden /> Спросить вслух
          </a>
        </div>
        <a className="hire-phone" href="tel:+78005550000">
          <Phone aria-hidden /> 8 800 555-00-00
        </a>
      </section>

      <StickyMobileCTA />

      <footer className="v2-footer hire-footer">
        <Link className="v2-logo" href="/v2">
          <DelnoMark />
          DELNO
        </Link>
        <p>
          Страница найма <code>/v2</code> · <Link href="/">dlno.ru</Link>
        </p>
        <div>
          <a href="#prices">Тарифы</a>
          <Link href="/privacy">Конфиденциальность</Link>
          <Link href="/terms">Соглашение</Link>
        </div>
        <small>© 2026 DELNO</small>
      </footer>
    </main>
  );
}
