import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  CalendarCheck,
  Check,
  ChevronDown,
  Clock3,
  Earth,
  FileText,
  Mail,
  MessageCircle,
  Phone,
  PhoneOutgoing,
  Send,
  ShieldCheck,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { LeadFormTrigger } from "../SiteControls";
import NeuralScene from "./NeuralScene";
import { V17PageShell } from "./V17PageShell";
import { BlogCardGrid } from "@/components/blog/BlogCardGrid";
import { blogPosts } from "@/lib/blogPosts";
import { mainPath } from "@/lib/landingPaths";

const faqItems: [string, string][] = [
  [
    "Какую работу можно поручить DELNO?",
    "Мы проверяем сценарии ответа на обращения, сбора заявки и передачи её ответственному. Для звонков, мессенджеров и записи состав действий, каналы и границы самостоятельности согласуем для вашей задачи.",
  ],
  [
    "Как быстро можно начать?",
    "Сначала выбираем одну задачу и считаем текущий поток обращений. Затем обсуждаем необходимые материалы, сроки и стоимость. Подключение начинаем после согласования конкретной задачи.",
  ],
  [
    "Можно подключить мой телефонный номер?",
    "Mango Office уже поддерживается. Возможность подключения другого городского или мобильного номера через SIP или переадресацию проверим до запуска. Условия и расходы на телефонию согласуем отдельно.",
  ],
  [
    "Что входит в стоимость?",
    "Цены на странице — ориентиры стоимости. Объём диалогов и звонков, стоимость настройки, телефонии и дополнительных минут проверяем под вашу задачу и согласуем до подключения.",
  ],
  [
    "Что происходит со сложными вопросами?",
    "Настраиваем правила уточнения и передачи обращения человеку. Сотрудник получает уже собранную информацию. Перед запуском проверяем типовые и сложные вопросы по вашей базе знаний; затем ответы можно корректировать.",
  ],
  [
    "Какие каналы можно подключить?",
    "Телефон, Telegram, MAX и почту. Плавающий помощник также работает на этом сайте. Подключение каждого канала к вашей компании согласуем отдельно; можно начать с одного.",
  ],
];

export default function V17Landing() {
  return (
    <V17PageShell>
      <section className="dv17-hero" id="product">
        <div className="dv17-hero-grid">
          <div className="dv17-hero-copy">
            <p className="dv17-eyebrow">
              <span className="dv17-presence-dot" /> ИИ-сотрудник на связи 24/7
            </p>
            <h1>
              ИИ-сотрудник для бизнеса.
              <br />
              <span>
                Ответ. Заявка.
                <br />
                Следующий шаг.
              </span>
            </h1>
            <p className="dv17-hero-description">
              DELNO принимает звонки и сообщения, консультирует по услугам и ценам из единой базы знаний,
              собирает заявки и передаёт их вашей команде. Начните с одного канала и одной задачи.
            </p>
            <div className="dv17-hero-actions">
              <a className="dv17-button dv17-primary dv17-try-button" href="#scenarios">
                Выбрать свою задачу <ArrowRight size={18} aria-hidden />
              </a>
              <LeadFormTrigger
                className="dv17-demo-link dv17-hero-contact"
                label="Оставить заявку"
                source="V17 hero contact"
              />
            </div>
            <p className="dv17-try-note">Оставьте заявку: уточним вашу задачу и свяжемся с вами.</p>
            <div className="dv17-hero-prices">
              <a href="#prices">
                Диалоги <strong>2 990 ₽/мес.</strong>
              </a>
              <span aria-hidden>·</span>
              <a href="#prices">
                Со звонками <strong>5 990 ₽/мес.</strong>
              </a>
            </div>
            <p className="dv17-start-note">Начнём с одной задачи. Поможем с настройкой.</p>
          </div>
          <NeuralScene />
        </div>
      </section>

      <section className="dv17-section dv17-work" id="work">
        <div className="dv17-section-intro">
          <p className="dv17-eyebrow">Больше времени на ваше дело</p>
          <h2>
            Рутина — DELNO.
            <br />
            <span>Клиенты — вашей команде.</span>
          </h2>
          <p>
            Поручите ему повторяющиеся обращения.
            <br />
            Сотрудники смогут заняться тем, где нужен человек.
          </p>
        </div>
        <div className="dv17-capabilities">
          <article className="dv17-capability dv17-capability-phone">
            <div className="dv17-capability-number">01</div>
            <div className="dv17-capability-top">
              <span className="dv17-icon-tile dv17-tile-phone">
                <Phone size={22} aria-hidden />
              </span>
              <span>Секретарь и администратор</span>
            </div>
            <h3>
              Пропущенный звонок.
              <br />
              Потерянный клиент?
            </h3>
            <p>Принимает запрос, уточняет потребность и передаёт заявку на запись ответственному.</p>
            <div className="dv17-call-receipt">
              <div>
                <PhoneOutgoing size={18} aria-hidden />
                <span>Заявка на запись</span>
              </div>
              <span className="dv17-result">
                <Check size={15} aria-hidden /> Запрос передан
              </span>
            </div>
          </article>
          <article className="dv17-capability dv17-capability-messages">
            <div className="dv17-capability-number">02</div>
            <div className="dv17-capability-top">
              <span className="dv17-icon-tile dv17-tile-message">
                <MessageCircle size={22} aria-hidden />
              </span>
              <span>Первая линия поддержки</span>
            </div>
            <h3>
              Ответы без
              <br />
              ожидания.
            </h3>
            <p>Поможет с услугами, ценами и условиями в Telegram, MAX и почте. Соберёт информацию для вашей команды.</p>
            <div className="dv17-channel-signatures">
              <span className="dv17-sign-telegram">
                <Send size={24} aria-hidden />
                Telegram
              </span>
              <span className="dv17-sign-max">
                <MessageCircle size={24} aria-hidden />
                MAX
              </span>
              <span className="dv17-sign-mail">
                <Mail size={24} aria-hidden />
                Почта
              </span>
            </div>
          </article>
          <article className="dv17-capability dv17-capability-wide">
            <div>
              <div className="dv17-capability-top">
                <CalendarCheck size={26} aria-hidden />
                <span>Помощник по записи</span>
              </div>
              <h3>
                От первого вопроса
                <br />
                до заявки.
              </h3>
              <p>
                Уточнение услуги и удобного времени помогает передать заявку с контекстом. Подтверждение визита
                возможно только после проверки расписания и правил бизнеса.
              </p>
            </div>
            <div className="dv17-booking-preview">
              <span className="dv17-example-label">Пример результата</span>
              <div className="dv17-booking-date">
                <CalendarCheck aria-hidden />
                <div>
                  <strong>Консультация</strong>
                  <span>Желаемое время: завтра, 16:30</span>
                </div>
              </div>
              <div className="dv17-booking-bottom">
                <span>Ожидает подтверждения</span>
                <Check size={18} aria-hidden />
              </div>
            </div>
          </article>
        </div>
      </section>

      <section className="dv17-section dv17-industries" id="scenarios">
        <div className="dv17-section-intro">
          <p className="dv17-eyebrow">Узнайте свой бизнес</p>
          <h2>
            Одна задача.
            <br />
            <span>Уже меньше работы.</span>
          </h2>
          <p>
            Выберите проблему, которую хотите решить первой. Поможем определить следующий шаг для вашей ситуации.
          </p>
        </div>
        <div className="dv17-market-scenarios">
          <Link href="/solutions/booking"><strong>Запись клиентов</strong><span>Как не терять запрос на запись и отличать заявку от подтверждённого визита.</span><span>Изучить сценарий →</span></Link>
          <Link href="/solutions/salon"><strong>Для салона красоты</strong><span>Запросы между процедурами, вечерние сообщения и переносы без путаницы в расписании.</span><span>Изучить сценарий →</span></Link>
          <Link href="/blog/no-show-cost"><strong>Неявки и пустые слоты</strong><span>Как оценить потери по своему расписанию и выбрать первую меру.</span><span>Разобрать задачу →</span></Link>
        </div>
      </section>

      <section className="dv17-knowledge dv17-section" id="knowledge">
        <div className="dv17-knowledge-copy">
          <p className="dv17-eyebrow">Единая база знаний</p>
          <h2>
            Одна информация.
            <br />
            <span>Каждый канал.</span>
          </h2>
          <p>
            Передайте сайт, прайс и правила работы. DELNO использует одну базу знаний в звонках, мессенджерах и
            письмах.
          </p>
          <p className="dv17-knowledge-secondary">
            Обновляйте цены и условия в одной базе. После обновления помощник использует эти данные во всех
            подключённых каналах.
          </p>
          <a className="dv17-inline-link" href="#launch">
            Как устроен запуск <ArrowRight size={18} aria-hidden />
          </a>
        </div>
        <div className="dv17-knowledge-map">
          <div className="dv17-knowledge-map-head">
            <span>
              <BookOpen size={19} aria-hidden />
              База знаний DELNO
            </span>
            <small>
              <i /> Пример базы
            </small>
          </div>
          <div className="dv17-knowledge-flow">
            <div className="dv17-knowledge-inputs">
              <span>
                <Earth aria-hidden /> Сайт
              </span>
              <span>
                <FileText aria-hidden /> Прайсы
              </span>
              <span>
                <ShieldCheck aria-hidden /> Правила
              </span>
            </div>
            <div className="dv17-knowledge-core">
              <div>
                <Image src="/delno-mark.svg" alt="" width={38} height={37} />
                <span>
                  ЗНАЕТ
                  <br />
                  ВАШ БИЗНЕС
                </span>
              </div>
            </div>
            <div className="dv17-knowledge-outputs">
              <span className="dv17-output-phone">
                <Phone aria-hidden /> Звонки
              </span>
              <span className="dv17-output-telegram">
                <Send aria-hidden /> Telegram
              </span>
              <span className="dv17-output-max">
                <MessageCircle aria-hidden /> MAX
              </span>
              <span className="dv17-output-mail">
                <Mail aria-hidden /> Почта
              </span>
            </div>
          </div>
          <div className="dv17-knowledge-insight">
            <Check size={17} aria-hidden />
            <span>Одни услуги, цены и правила во всех каналах</span>
          </div>
        </div>
      </section>

      <section className="dv17-section dv17-launch" id="launch">
        <div className="dv17-section-intro">
          <p className="dv17-eyebrow">Поможем на каждом шаге</p>
          <h2>
            Начать проще,
            <br />
            <span>чем нанять сотрудника.</span>
          </h2>
          <p>
            Начнём с задачи и ожидаемого результата.
            <br />
            Вы знаете свой бизнес. Мы поможем оценить сценарий и его экономику.
          </p>
        </div>
        <ol className="dv17-steps">
          <li>
            <span>01</span>
            <h3>Выберите задачу</h3>
            <p>Например, подтверждать записи или отвечать на входящие звонки.</p>
          </li>
          <li>
            <span>02</span>
            <h3>Оцените поток</h3>
            <p>Сколько обращений приходит, сколько остаётся без ответа и сколько превращается в запись.</p>
          </li>
          <li>
            <span>03</span>
            <h3>Расскажите о своей задаче</h3>
            <p>Согласуем результат, сроки и цену только для сценария, который имеет смысл проверять.</p>
          </li>
        </ol>
        <div className="dv17-launch-bottom">
          <span>
            <Clock3 size={18} aria-hidden /> Сначала спрос и расчёт, затем подключение
          </span>
          <LeadFormTrigger className="dv17-inline-link" label="Оставить заявку" source="V17 launch" />
        </div>
      </section>

      <section className="dv17-section dv17-pricing" id="prices">
        <div className="dv17-section-intro">
          <p className="dv17-eyebrow">Ориентиры для разговора</p>
          <h2>
            Одна задача.
            <br />
            <span>Понятный объём работы.</span>
          </h2>
          <p>
            Обсудим нужный канал и объём.
            <br />
            Окончательные условия определим после расчёта.
          </p>
        </div>
        <div className="dv17-price-grid">
          <article className="dv17-plan">
            <span className="dv17-plan-type">Диалоги</span>
            <h3>
              2 990 <span>₽/мес.</span>
            </h3>
            <p>Когда клиенты пишут.</p>
            <ul>
              <li>
                <Check aria-hidden /> До 300 ИИ-диалогов в месяц
              </li>
              <li>
                <Check aria-hidden /> Поддерживаемые мессенджеры
              </li>
              <li>
                <Check aria-hidden /> Общая база знаний
              </li>
              <li>
                <Check aria-hidden /> История обращений и запись
              </li>
            </ul>
            <LeadFormTrigger className="dv17-button dv17-secondary" label="Обсудить диалоги" source="V17 plan 2990" />
            <small>Без телефонных звонков</small>
          </article>
          <article className="dv17-plan dv17-plan-featured">
            <div className="dv17-plan-badge">Входящие + исходящие</div>
            <span className="dv17-plan-type">Диалоги + звонки</span>
            <h3>
              5 990 <span>₽/мес.</span>
            </h3>
            <p>Когда нужен ИИ-сотрудник на связи.</p>
            <ul>
              <li>
                <Check aria-hidden /> Всё из тарифа «Диалоги»
              </li>
              <li>
                <Check aria-hidden /> 100 минут телефонных разговоров
              </li>
              <li>
                <Check aria-hidden /> Входящие и исходящие звонки
              </li>
              <li>
                <Check aria-hidden /> Итоги звонков и передача человеку
              </li>
            </ul>
            <LeadFormTrigger className="dv17-button dv17-primary" label="Обсудить звонки" source="V17 plan 5990" />
            <small>Дополнительные минуты — отдельно</small>
          </article>
          <article className="dv17-plan">
            <span className="dv17-plan-type">Компания</span>
            <h3 className="dv17-custom-price">Индивидуально</h3>
            <p>Для нескольких точек и ваших систем.</p>
            <ul>
              <li>
                <Check aria-hidden /> Несколько номеров и филиалов
              </li>
              <li>
                <Check aria-hidden /> Роли для сотрудников
              </li>
              <li>
                <Check aria-hidden /> Интеграции с вашими системами
              </li>
              <li>
                <Check aria-hidden /> Индивидуальные сценарии
              </li>
            </ul>
            <LeadFormTrigger
              className="dv17-button dv17-secondary"
              label="Обсудить подключение"
              source="V17 plan enterprise"
            />
            <small>Под задачи и объём компании</small>
          </article>
        </div>
        <p className="dv17-pricing-note">
          Цены — ориентиры для проверки спроса, не публичная оферта. Состав работы и итоговую цену согласуем отдельно.
          <br />
          Телефонию, дополнительные объёмы, настройку и интеграции считаем под вашу задачу.
        </p>
      </section>

      <section className="dv17-section dv17-blog-preview" id="blog">
        <div>
          <p className="dv17-eyebrow">Блог DELNO</p>
          <h2>
            Как поручить рутину ИИ
            <br />
            <span>и сохранить качество сервиса.</span>
          </h2>
          <p>Разбираем сценарии, подготовку базы знаний и запуск ИИ-сотрудника без сложных терминов.</p>
          <Link href={mainPath("/blog")} className="dv17-inline-link">
            Читать статьи <ArrowRight size={18} aria-hidden />
          </Link>
        </div>
        <BlogCardGrid posts={blogPosts.filter((post) => ["chatbot-cost-for-business", "chatbot-for-website-checklist"].includes(post.slug))} />
      </section>

      <section className="dv17-section dv17-faq" id="answers">
        <div>
          <p className="dv17-eyebrow">До знакомства</p>
          <h2>
            Вопросы?
            <br />
            <span>По делу.</span>
          </h2>
        </div>
        <div className="dv17-faq-list">
          {faqItems.map(([q, a]) => (
            <details key={q}>
              <summary>
                {q}
                <ChevronDown size={20} aria-hidden />
              </summary>
              <p>{a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="dv17-final" id="contact">
        <div className="dv17-final-mark">
          <Image src="/delno-mark.svg" alt="" width={48} height={46} />
        </div>
        <p className="dv17-eyebrow">Ваш следующий шаг</p>
        <h2>
          Покажите задачу.
          <br />
          Мы покажем решение.
        </h2>
        <p>
          Разберём ваши обращения и предложим первый сценарий
          <br />
          для DELNO. Начать можно с одного канала.
        </p>
        <div className="dv17-final-actions">
          <LeadFormTrigger
            className="dv17-button dv17-primary"
            label="Оставить заявку"
            source="V17 final"
          />
          <Link href="/solutions/booking" className="dv17-demo-link">
            Сначала изучить сценарий
          </Link>
        </div>
        <div className="dv17-direct-contacts">
          <a href="tel:+78005559418">
            8 800 555-94-18 <Phone size={15} aria-hidden />
          </a>
          <a href="https://t.me/Dlno_bot" target="_blank" rel="noreferrer">
            Telegram <ArrowUpRight size={15} aria-hidden />
          </a>
          <a href="https://max.ru/id471405233378_bot" target="_blank" rel="noreferrer">
            MAX <ArrowUpRight size={15} aria-hidden />
          </a>
          <a href="mailto:office@dlno.ru">
            Почта <ArrowUpRight size={15} aria-hidden />
          </a>
        </div>
      </section>
    </V17PageShell>
  );
}
