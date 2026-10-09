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
  Menu,
  MessageCircle,
  Phone,
  PhoneOutgoing,
  Send,
  ShieldCheck,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import VoiceDemo from "../VoiceDemo";
import { LeadFormTrigger } from "../SiteControls";
import NeuralScene from "./NeuralScene";
import V15IndustryTabs from "./V15IndustryTabs";

const faqItems: [string, string][] = [
  [
    "Какую работу можно поручить DELNO?",
    "Приём входящих звонков, ответы в мессенджерах и почте, консультации по вашим материалам, сбор заявок и запись. Исходящие звонки можно использовать для подтверждения визита или связи по оставленной заявке. Сценарии и границы самостоятельности согласуем при подключении.",
  ],
  [
    "Как быстро можно начать?",
    "Начинаем с одного канала и одной задачи. Вы передаёте сайт, прайс и правила работы, мы настраиваем помощника и вместе проверяем ответы. Первый сценарий обычно занимает несколько дней; точный срок зависит от материалов и интеграций.",
  ],
  [
    "Можно подключить мой телефонный номер?",
    "Mango Office уже поддерживается. Возможность подключения другого городского или мобильного номера через SIP или переадресацию проверим до запуска. Условия и расходы на телефонию согласуем отдельно.",
  ],
  [
    "Что входит в стоимость?",
    "«Диалоги» — до 300 ИИ-диалогов в месяц, поддерживаемые мессенджеры и общая база знаний. «Диалоги + звонки» добавляют 100 минут входящих и исходящих разговоров. Стоимость дополнительных минут, отправок, настройки и нестандартных интеграций уточняем до подключения.",
  ],
  [
    "Что происходит со сложными вопросами?",
    "Настраиваем правила уточнения и передачи обращения человеку. Сотрудник получает уже собранную информацию. Перед запуском проверяем типовые и сложные вопросы по вашей базе знаний; затем ответы можно корректировать.",
  ],
  [
    "Какие каналы можно подключить?",
    "Телефон, Telegram, MAX и почту. Подключение MAX зависит от доступности и требований платформы. Виджет для сайта развиваем отдельно — его доступность для вашего проекта уточним при подключении. Можно начать с одного канала.",
  ],
];

export default function V15Landing() {
  return (
    <main className="delno-v15">
      <header className="dv15-header">
        <div className="dv15-nav-wrap">
          <Link href="/v2" className="dv15-brand" aria-label="DELNO — главная">
            <Image src="/delno-mark.svg" width={29} height={28} alt="" />
            DELNO
          </Link>
          <nav className="dv15-desktop-nav" aria-label="Разделы сайта">
            <a href="#work">Как работает</a>
            <a href="#scenarios">Сценарии</a>
            <a href="#prices">Стоимость</a>
            <Link href="/">Основной сайт</Link>
            <a href="#contact">Контакты</a>
          </nav>
          <div className="dv15-nav-actions">
            <a className="dv15-button dv15-button-small" href="#demo">
              Попробовать
            </a>
            <div className="dv15-mobile-nav">
              <button type="button" className="dv15-menu-toggle" aria-label="Меню">
                <Menu aria-hidden />
              </button>
            </div>
          </div>
        </div>
      </header>

      <section className="dv15-hero" id="product">
        <div className="dv15-hero-grid">
          <div className="dv15-hero-copy">
            <p className="dv15-eyebrow">
              <span className="dv15-presence-dot" /> ИИ-сотрудник на связи 24/7
            </p>
            <h1>
              Ваш ИИ-сотрудник.
              <br />
              <span>
                Звонит. Отвечает.
                <br />
                Записывает.
              </span>
            </h1>
            <p className="dv15-hero-description">
              Пока команда занята, DELNO принимает звонки и сообщения, отвечает по вашей базе знаний и
              записывает клиентов. На связи 24/7.
            </p>
            <div className="dv15-hero-actions">
              <a className="dv15-button dv15-primary dv15-try-button" href="#demo">
                Попробовать DELNO <ArrowRight size={18} aria-hidden />
              </a>
              <LeadFormTrigger
                className="dv15-demo-link dv15-hero-contact"
                label="Хочу попробовать у себя"
                source="V15 hero contact"
              />
            </div>
            <p className="dv15-try-note">Демо прямо здесь · без регистрации</p>
            <div className="dv15-hero-prices">
              <a href="#prices">
                Диалоги <strong>2 990 ₽/мес.</strong>
              </a>
              <span aria-hidden>·</span>
              <a href="#prices">
                Со звонками <strong>5 990 ₽/мес.</strong>
              </a>
            </div>
            <p className="dv15-start-note">Начнём с одной задачи. Поможем с настройкой.</p>
          </div>
          <NeuralScene />
        </div>
      </section>

      <section className="dv15-live-demo">
        <VoiceDemo variant="v15" />
        <div className="dv15-after-demo">
          <p>Хотите услышать DELNO с вашими услугами и правилами?</p>
          <LeadFormTrigger
            className="dv15-button dv15-primary"
            label="Хочу попробовать у себя"
            source="V15 after demo"
          />
        </div>
      </section>

      <section className="dv15-section dv15-work" id="work">
        <div className="dv15-section-intro">
          <p className="dv15-eyebrow">Больше времени на ваше дело</p>
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
        <div className="dv15-capabilities">
          <article className="dv15-capability dv15-capability-phone">
            <div className="dv15-capability-number">01</div>
            <div className="dv15-capability-top">
              <span className="dv15-icon-tile dv15-tile-phone">
                <Phone size={22} aria-hidden />
              </span>
              <span>Секретарь и администратор</span>
            </div>
            <h3>
              Каждый звонок.
              <br />
              Следующий шаг.
            </h3>
            <p>Ответит на входящий, уточнит запрос и предложит запись. Сам позвонит, чтобы подтвердить визит.</p>
            <div className="dv15-call-receipt">
              <div>
                <PhoneOutgoing size={18} aria-hidden />
                <span>Подтверждение записи</span>
              </div>
              <span className="dv15-result">
                <Check size={15} aria-hidden /> Визит подтверждён
              </span>
            </div>
          </article>
          <article className="dv15-capability dv15-capability-messages">
            <div className="dv15-capability-number">02</div>
            <div className="dv15-capability-top">
              <span className="dv15-icon-tile dv15-tile-message">
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
            <div className="dv15-channel-signatures">
              <span className="dv15-sign-telegram">
                <Send size={24} aria-hidden />
                Telegram
              </span>
              <span className="dv15-sign-max">
                <MessageCircle size={24} aria-hidden />
                MAX
              </span>
              <span className="dv15-sign-mail">
                <Mail size={24} aria-hidden />
                Почта
              </span>
            </div>
          </article>
          <article className="dv15-capability dv15-capability-wide">
            <div>
              <div className="dv15-capability-top">
                <CalendarCheck size={26} aria-hidden />
                <span>Помощник по записи</span>
              </div>
              <h3>
                От первого вопроса
                <br />
                до встречи.
              </h3>
              <p>
                Уточнит услугу, предложит свободное время и сохранит запись. По согласованному сценарию напомнит о
                встрече и зафиксирует ответ.
              </p>
            </div>
            <div className="dv15-booking-preview">
              <span className="dv15-example-label">Пример результата</span>
              <div className="dv15-booking-date">
                <CalendarCheck aria-hidden />
                <div>
                  <strong>Консультация</strong>
                  <span>Завтра, 16:30</span>
                </div>
              </div>
              <div className="dv15-booking-bottom">
                <span>Запись в календаре</span>
                <Check size={18} aria-hidden />
              </div>
            </div>
          </article>
        </div>
      </section>

      <section className="dv15-section dv15-industries" id="scenarios">
        <div className="dv15-section-intro">
          <p className="dv15-eyebrow">Узнайте свой бизнес</p>
          <h2>
            Одна задача.
            <br />
            <span>Уже меньше работы.</span>
          </h2>
          <p>
            Посмотрите, как DELNO может подтвердить запись
            <br />
            или согласовать следующий шаг с клиентом.
          </p>
        </div>
        <V15IndustryTabs />
      </section>

      <section className="dv15-knowledge dv15-section" id="knowledge">
        <div className="dv15-knowledge-copy">
          <p className="dv15-eyebrow">Единая база знаний</p>
          <h2>
            Одна информация.
            <br />
            <span>Каждый канал.</span>
          </h2>
          <p>
            Передайте сайт, прайс и правила работы. DELNO использует одну базу знаний в звонках, мессенджерах и
            письмах.
          </p>
          <p className="dv15-knowledge-secondary">
            Обновляйте цены и условия в одной базе. После обновления помощник использует эти данные во всех
            подключённых каналах.
          </p>
          <a className="dv15-inline-link" href="#launch">
            Как устроен запуск <ArrowRight size={18} aria-hidden />
          </a>
        </div>
        <div className="dv15-knowledge-map">
          <div className="dv15-knowledge-map-head">
            <span>
              <BookOpen size={19} aria-hidden />
              База знаний DELNO
            </span>
            <small>
              <i /> Пример базы
            </small>
          </div>
          <div className="dv15-knowledge-flow">
            <div className="dv15-knowledge-inputs">
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
            <div className="dv15-knowledge-core">
              <div>
                <Image src="/delno-mark.svg" alt="" width={38} height={37} />
                <span>
                  ЗНАЕТ
                  <br />
                  ВАШ БИЗНЕС
                </span>
              </div>
            </div>
            <div className="dv15-knowledge-outputs">
              <span className="dv15-output-phone">
                <Phone aria-hidden /> Звонки
              </span>
              <span className="dv15-output-telegram">
                <Send aria-hidden /> Telegram
              </span>
              <span className="dv15-output-max">
                <MessageCircle aria-hidden /> MAX
              </span>
              <span className="dv15-output-mail">
                <Mail aria-hidden /> Почта
              </span>
            </div>
          </div>
          <div className="dv15-knowledge-insight">
            <Check size={17} aria-hidden />
            <span>Одни услуги, цены и правила во всех каналах</span>
          </div>
        </div>
      </section>

      <section className="dv15-section dv15-launch" id="launch">
        <div className="dv15-section-intro">
          <p className="dv15-eyebrow">Поможем на каждом шаге</p>
          <h2>
            Начать проще,
            <br />
            <span>чем нанять сотрудника.</span>
          </h2>
          <p>
            Не нужно разбираться в настройках ИИ.
            <br />
            Вы знаете свой бизнес. Мы поможем научить ему DELNO.
          </p>
        </div>
        <ol className="dv15-steps">
          <li>
            <span>01</span>
            <h3>Выберите задачу</h3>
            <p>Например, подтверждать записи или отвечать на входящие звонки.</p>
          </li>
          <li>
            <span>02</span>
            <h3>Передайте материалы</h3>
            <p>Сайт, прайс и правила. Подключим канал и настроим ответы.</p>
          </li>
          <li>
            <span>03</span>
            <h3>Проверьте и запускайте</h3>
            <p>Вместе проверим диалоги. После запуска можно расширять задачи.</p>
          </li>
        </ol>
        <div className="dv15-launch-bottom">
          <span>
            <Clock3 size={18} aria-hidden /> Первый сценарий — обычно за несколько дней
          </span>
          <LeadFormTrigger className="dv15-inline-link" label="Хочу попробовать у себя" source="V15 launch" />
        </div>
      </section>

      <section className="dv15-section dv15-pricing" id="prices">
        <div className="dv15-section-intro">
          <p className="dv15-eyebrow">Понятная стоимость</p>
          <h2>
            Новый сотрудник.
            <br />
            <span>Без новой ставки в штате.</span>
          </h2>
          <p>
            Начните с нужных каналов.
            <br />
            Расширяйте возможности по мере роста.
          </p>
        </div>
        <div className="dv15-price-grid">
          <article className="dv15-plan">
            <span className="dv15-plan-type">Диалоги</span>
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
            <LeadFormTrigger className="dv15-button dv15-secondary" label="Начать с диалогов" source="V15 plan 2990" />
            <small>Без телефонных звонков</small>
          </article>
          <article className="dv15-plan dv15-plan-featured">
            <div className="dv15-plan-badge">Входящие + исходящие</div>
            <span className="dv15-plan-type">Диалоги + звонки</span>
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
            <LeadFormTrigger className="dv15-button dv15-primary" label="Обсудить звонки" source="V15 plan 5990" />
            <small>Дополнительные минуты — отдельно</small>
          </article>
          <article className="dv15-plan">
            <span className="dv15-plan-type">Компания</span>
            <h3 className="dv15-custom-price">Индивидуально</h3>
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
              className="dv15-button dv15-secondary"
              label="Обсудить подключение"
              source="V15 plan enterprise"
            />
            <small>Под задачи и объём компании</small>
          </article>
        </div>
        <p className="dv15-pricing-note">
          Телефонию, дополнительные объёмы, настройку и интеграции согласуем до запуска.
          <br />
          Подключение почты и доступность виджета для сайта уточним под вашу задачу.
        </p>
      </section>

      <section className="dv15-section dv15-faq" id="answers">
        <div>
          <p className="dv15-eyebrow">До знакомства</p>
          <h2>
            Вопросы?
            <br />
            <span>По делу.</span>
          </h2>
        </div>
        <div className="dv15-faq-list">
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

      <section className="dv15-final" id="contact">
        <div className="dv15-final-mark">
          <Image src="/delno-mark.svg" alt="" width={48} height={46} />
        </div>
        <p className="dv15-eyebrow">Ваш следующий шаг</p>
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
        <div className="dv15-final-actions">
          <LeadFormTrigger
            className="dv15-button dv15-primary"
            label="Хочу попробовать у себя"
            source="V15 final"
          />
          <a href="#demo" className="dv15-demo-link">
            Сначала попробовать демо
          </a>
        </div>
        <div className="dv15-direct-contacts">
          <a href="https://t.me/Dlno_bot" target="_blank" rel="noreferrer">
            Telegram <ArrowUpRight size={15} aria-hidden />
          </a>
          <a href="https://max.ru/@id471405233378_bot" target="_blank" rel="noreferrer">
            MAX <ArrowUpRight size={15} aria-hidden />
          </a>
          <a href="mailto:office@dlno.ru">
            Почта <ArrowUpRight size={15} aria-hidden />
          </a>
        </div>
      </section>

      <footer className="dv15-footer">
        <div>
          <Link href="/v2" className="dv15-brand">
            <Image src="/delno-mark.svg" width={26} height={25} alt="" />
            DELNO
          </Link>
          <span>ИИ-сотрудник для работы с клиентами.</span>
        </div>
        <div>
          <Link href="/">dlno.ru</Link>
          <Link href="/privacy">Конфиденциальность</Link>
          <Link href="/terms">Пользовательское соглашение</Link>
          <span>© 2026 DELNO</span>
        </div>
      </footer>
    </main>
  );
}
