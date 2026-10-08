import { Check, Mic, Phone, Play } from "lucide-react";
import Link from "next/link";
import "./v2.css";
import "./mobile.css";
import { DelnoMark, V4ProductStage } from "./DelnoPage";
import { FaqSection, type FaqItem } from "./FaqSection";
import VoiceDemo from "./VoiceDemo";
import { LeadFormTrigger } from "./SiteControls";
import {
  ConvertPricingNote,
  ConvertTrustBar,
  StickyMobileCTA,
} from "./SiteConvert";

const convertFaq: FaqItem[] = [
  [
    "Что входит в 300 диалогов?",
    "Считаются отдельные ИИ-диалоги с клиентом, а не каждое сообщение внутри одного разговора. Лимит одинаковый на тарифах «Диалоги» и «Диалоги + звонки».",
  ],
  [
    "Что входит в тариф за 2 990 ₽?",
    "Чат и голосовой виджет на сайте, мессенджеры, база знаний, до 300 ИИ-диалогов и 30 минут голоса в виджете. Обычные телефонные звонки (PSTN) не входят.",
  ],
  [
    "Когда нужен тариф 5 990 ₽?",
    "Когда клиенты звонят на номер или нужны исходящие звонки. В пакет входят 100 минут телефонии и всё из тарифа «Диалоги».",
  ],
  [
    "Можно попробовать до оплаты?",
    "Да. Ниже на странице — голосовое демо с той же логикой, что на вашем сайте. Для запуска на вашем бизнесе оставьте заявку — подготовим демо-сценарий.",
  ],
  [
    "DELNO придумает ответ, если не знает?",
    "Нет. Уточнит вопрос или передаст обращение человеку вместе с уже собранным контекстом.",
  ],
];

export default function ConvertLanding() {
  return (
    <main className="v2 v4-refined v2-convert v2-convert-page">
      <header className="v2-header cvt-header">
        <Link className="v2-logo" href="/v2">
          <DelnoMark />
          DELNO
        </Link>
        <nav className="cvt-nav" aria-label="Разделы страницы">
          <a href="#demo">Демо</a>
          <a href="#compare">Сравнение</a>
          <a href="#prices">Тарифы</a>
          <a href="#answers">Вопросы</a>
        </nav>
        <div className="v2-header-right">
          <a className="header-convert-cta" href="#demo">
            Попробовать бесплатно
          </a>
          <LeadFormTrigger className="v2-btn compact" label="Демо" source="Header v2-convert" />
        </div>
      </header>

      <section className="cvt-hero" id="product">
        <div className="cvt-hero-inner">
          <p className="cvt-eyebrow">Клиники · салоны · сервис с потоком обращений</p>
          <h1>
            Клиенты пишут и звонят —
            <span> DELNO закрывает первую линию.</span>
          </h1>
          <p className="cvt-lead">
            Ответы из вашей базы знаний на сайте, в мессенджерах и (по тарифу) по телефону.
            В пакете уже <strong>300 диалогов</strong> и <strong>30 минут</strong> голоса на сайте — без
            найма ещё одного администратора.
          </p>
          <div className="v2-actions cvt-actions">
            <a className="v2-btn primary" href="#demo">
              <Mic aria-hidden />
              Спросить вслух (30 сек)
            </a>
            <LeadFormTrigger
              className="v2-btn secondary"
              label="Демо на моём бизнесе"
              source="Hero v2-convert"
            />
          </div>
          <p className="cvt-micro">
            Без карты · <Link href="/">Классическая версия сайта</Link>
          </p>
        </div>
        <div className="cvt-hero-visual">
          <V4ProductStage />
        </div>
      </section>

      <ConvertTrustBar />

      <VoiceDemo />

      <section className="cvt-compare v2-section" id="compare">
        <div className="v2-kicker">Экономика первой линии</div>
        <h2 className="cvt-h2">
          Три смены администраторов
          <br />
          <span>или один DELNO в пакете.</span>
        </h2>
        <p className="cvt-compare-lead">
          Оценка для ориентира — не оферта. DELNO не заменяет врача или мастера, но снимает
          повторяющиеся обращения: цены, запись, «вы работаете в субботу?».
        </p>
        <div className="cvt-compare-table" role="table">
          <div className="cvt-row cvt-head" role="row">
            <span role="columnheader" />
            <span role="columnheader">3 администратора</span>
            <span role="columnheader">DELNO «Диалоги + звонки»</span>
          </div>
          <div className="cvt-row" role="row">
            <span role="rowheader">Ежемесячные затраты</span>
            <span>от ~150 000 ₽ ФОТ + налоги</span>
            <span className="cvt-highlight">5 990 ₽ абонент</span>
          </div>
          <div className="cvt-row" role="row">
            <span role="rowheader">Ночь и выходные</span>
            <span>смены / пропуски</span>
            <span className="cvt-highlight">24/7 на подключённых каналах</span>
          </div>
          <div className="cvt-row" role="row">
            <span role="rowheader">Объём в пакете</span>
            <span>зависит от людей</span>
            <span className="cvt-highlight">300 диалогов + 100 мин PSTN</span>
          </div>
          <div className="cvt-row" role="row">
            <span role="rowheader">Единая база для каналов</span>
            <span>часто разрозненно</span>
            <span className="cvt-highlight">одна KB для сайта и чатов</span>
          </div>
        </div>
        <LeadFormTrigger
          className="v2-btn primary cvt-compare-cta"
          label="Посчитать для моего бизнеса"
          source="Блок сравнения v2"
        />
      </section>

      <section className="cvt-steps v2-section">
        <div className="v2-kicker">Как начать</div>
        <ol className="cvt-step-list">
          <li>
            <span>1</span>
            <div>
              <b>Проверьте голосом</b>
              <p>Задайте вопрос про тарифы или запись — как ваш клиент.</p>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <b>Оставьте заявку</b>
              <p>Подберём один сценарий: сайт, Telegram или звонки.</p>
            </div>
          </li>
          <li>
            <span>3</span>
            <div>
              <b>Запуск на ваших материалах</b>
              <p>Услуги, цены, правила — одна база для всех каналов.</p>
            </div>
          </li>
        </ol>
      </section>

      <section className="v2-pricing cvt-pricing" id="prices">
        <div className="v2-pricing-head">
          <div className="v2-kicker pale">Прозрачные пакеты</div>
          <h2>Выберите, как клиенты обращаются</h2>
          <p>Лимиты видны сразу — без «уточним по телефону».</p>
        </div>
        <ConvertPricingNote />
        <div className="v2-price-grid cvt-price-grid">
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
            <LeadFormTrigger className="price-lead" label="Начать с чатов" source="Convert 2990" />
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
            <LeadFormTrigger className="price-lead" label="Получить демо" source="Convert 5990" />
          </article>
        </div>
      </section>

      <FaqSection fallback={convertFaq} version4 />

      <section className="v2-final cvt-final" id="contact">
        <div className="final-glow" />
        <h2>
          Проверьте DELNO
          <span> до найма ещё одного администратора.</span>
        </h2>
        <p>Сначала голос на этой странице — затем демо на примере вашего бизнеса.</p>
        <div className="cvt-final-actions">
          <a className="v2-btn primary" href="#demo">
            <Play aria-hidden /> Спросить вслух
          </a>
          <LeadFormTrigger className="v2-btn final-lead" label="Получить демо" source="Финал v2-convert" />
        </div>
        <a className="cvt-phone" href="tel:+78005550000">
          <Phone aria-hidden /> 8 800 555-00-00
        </a>
      </section>

      <StickyMobileCTA />

      <footer className="v2-footer">
        <Link className="v2-logo" href="/v2">
          <DelnoMark />
          DELNO
        </Link>
        <p>
          Conversion landing <code>/v2</code> ·{" "}
          <Link href="/">Основной сайт</Link>
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
