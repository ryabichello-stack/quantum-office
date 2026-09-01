import { ArrowRight, CalendarDays, Check, ChevronRight, CircleCheck, FileText, Globe, Mail, MessageCircle, Mic, Phone, Play, Search, Send, ShieldCheck, Sparkles, UserRound, Zap } from "lucide-react";
import Link from "next/link";
import "./v2.css";
import { ActiveNav, LeadFormTrigger } from "./SiteControls";
import { FaqSection } from "./FaqSection";
import VoiceDemo from "./VoiceDemo";
import ScenarioSwitcher from "./ScenarioSwitcher";

const features=[
  {icon:Phone,title:"Разговаривает",text:"Принимает входящие и выполняет исходящие звонки. Уточняет запрос, отвечает и фиксирует результат.",tag:"Телефон"},
  {icon:MessageCircle,title:"Переписывается",text:"Продолжает единый диалог на сайте, в Telegram, MAX и других подключённых мессенджерах.",tag:"Чаты"},
  {icon:CalendarDays,title:"Записывает",text:"Видит свободное время, создаёт запись и отправляет клиенту напоминание.",tag:"Календарь"},
  {icon:Mail,title:"Ведёт почту",text:"Разбирает входящие обращения и запускает согласованные цепочки писем.",tag:"Почта"},
];
const v4Features=[
  {icon:MessageCircle,title:"Отвечает",text:"Встречает клиента на сайте и в мессенджерах, отвечает на типовые вопросы и принимает контакты.",tag:"Первая линия"},
  {icon:FileText,title:"Консультирует",text:"Использует ваши услуги, цены, правила и документы — одну базу знаний для всех каналов.",tag:"Знания"},
  {icon:CalendarDays,title:"Записывает",text:"Уточняет услугу и время, создаёт запись и отправляет клиенту подтверждение.",tag:"Календарь"},
  {icon:Phone,title:"Разговаривает",text:"В тарифе «Диалоги + звонки» принимает входящие и выполняет согласованные исходящие звонки.",tag:"Телефон"},
];
const clientChannels=[
  {icon:Globe,label:"Сайт",tone:"web",href:"#demo"},
  {icon:Phone,label:"Звонки",tone:"phone",href:"tel:+78005550000"},
  {icon:Send,label:"Telegram",tone:"telegram",href:"https://t.me/quantumlabss",external:true},
  {icon:MessageCircle,label:"MAX",tone:"max",href:"https://max.ru/id7840118071_bot",external:true},
  {icon:Mail,label:"Почта",tone:"mail",href:"mailto:hello@delno.one"},
];
const v4ClientChannels=[
  {icon:Globe,label:"Сайт",tone:"web",href:"#demo"},
  {icon:Phone,label:"Звонки",tone:"phone",href:"tel:+78005550000"},
  {icon:Send,label:"Telegram",tone:"telegram",href:"https://t.me/Dlno_bot",external:true},
  {icon:MessageCircle,label:"MAX",tone:"max",href:"https://max.ru/@id471405233378_bot",external:true},
  {icon:Mail,label:"Почта",tone:"mail",href:"mailto:office@dlno.ru"},
];
const faq=[
  ["Подключится ли DELNO к моему номеру?","Да, если оператор поддерживает SIP или переадресацию. Mango Office уже подключён. Для мобильного или городского номера подберём вариант после технической проверки."],
  ["Что входит в подписку, а что оплачивается отдельно?","В подписку входят кабинет, база знаний, история обращений, выбранные каналы и указанный в тарифе объём. Дополнительные минуты и массовые отправки оплачиваются только сверх включённого пакета."],
  ["Как научить его отвечать правильно?","В кабинете вы добавляете услуги, товары, цены, документы, правила и ответы. Одна база знаний используется во всех каналах."],
  ["Что, если DELNO не знает ответа?","Он не будет придумывать. Уточнит информацию или передаст обращение человеку вместе с контекстом разговора."],
  ["Какие мессенджеры можно подключить?","В первую очередь — Telegram и MAX. Другие мессенджеры подключаем, если у канала есть подходящий API или бот-интерфейс. История клиента и база знаний остаются общими."],
  ["Как DELNO появляется на сайте?","Можно установить чат, голосовую кнопку или единый виджет с обоими способами связи. Оформление адаптируем под дизайн сайта, а ответы берём из общей базы знаний."],
  ["Можно проверить голос до подключения?","Да. На этой странице уже работает демонстрационный помощник: выберите готовый вопрос или нажмите кнопку с микрофоном и спросите вслух."],
  ["С чего лучше начать запуск?","С одной понятной задачи: отвечать на вопросы на сайте, записывать клиентов или принимать звонки. После проверки первого сценария добавляем остальные каналы."],
];
const v4Faq=[
  ["Чем DELNO отличается от обычного чат-бота?","Обычный бот обычно работает в одном канале и по жёсткому сценарию. DELNO использует общую базу знаний для сайта, мессенджеров, почты и телефона, понимает свободный вопрос и сохраняет контекст обращения."],
  ["Что входит в тариф за 2 990 ₽?","«Диалоги» включают чат на сайте, поддерживаемые мессенджеры, общую базу знаний, до 300 ИИ-диалогов, голосовой виджет и 30 минут общения голосом на сайте. Обычные телефонные звонки в этот тариф не входят."],
  ["Когда нужен тариф за 5 990 ₽?","Когда клиенты звонят или вам нужны исходящие звонки. «Диалоги + звонки» включают всё из базового тарифа, входящие и исходящие телефонные разговоры, 100 минут и передачу обращения человеку."],
  ["Можно ли начать только с одного канала?","Да. Например, сначала подключить чат на сайт или Telegram. Это не отдельный тариф: вы выбираете первую задачу внутри подходящего тарифа, проверяете результат и затем добавляете другие каналы."],
  ["Как DELNO узнаёт информацию о компании?","Вы передаёте сайт, услуги, цены, документы, инструкции и ответы на частые вопросы. Эти материалы становятся единой базой знаний для всех подключённых каналов."],
  ["Что происходит, если DELNO не знает ответа?","Он работает в заданных границах: уточняет вопрос или передаёт обращение человеку вместе с уже собранным контекстом."],
  ["Как подключается телефон?","Сейчас поддерживается Mango Office. Другой городской или мобильный номер подключается через SIP или переадресацию после технической проверки."],
  ["Сколько занимает запуск?","Первый ограниченный сценарий обычно можно настроить за несколько дней. Срок зависит от канала, объёма базы знаний и необходимых интеграций."],
];

function DelnoMark({small=false}:{small?:boolean}){
  return <span className={small?"delno-mark mark-small":"delno-mark"} aria-hidden="true">
    <svg viewBox="0 0 895 847" focusable="false">
      <path d="M0 0h490c266 0 405 184 405 423S756 847 490 847H0V240h101l124 75v357h254c118 0 196-102 196-249 0-123-68-240-208-240H0V0Z"/>
    </svg>
  </span>
}

function V4ProductStage(){
  return <div className="v4-product-stage" aria-label="Как DELNO обрабатывает обращение клиента">
    <div className="v4-stage-grid" aria-hidden="true"/>
    <div className="v4-stage-channels">{v4ClientChannels.map(({icon:Icon,label,tone,href,external},index)=><a key={label} className={`stage-channel ${tone} channel-${index}`} href={href} target={external?"_blank":undefined} rel={external?"noreferrer":undefined}><i><Icon/></i><span>{label}</span></a>)}</div>
    <div className="v4-stage-orbit"><i/><i/><i/><div className="v4-core-orb"><DelnoMark small/><span>DELNO</span></div></div>
    <div className="v4-incoming"><small><Send/> Telegram · сейчас</small><b>«Можно записаться<br/>завтра вечером?»</b></div>
    <div className="v4-thinking"><Sparkles/><div><small>DELNO понял задачу</small><b>Проверить расписание<br/>и предложить время</b></div></div>
    <div className="v4-action"><CircleCheck/><div><small>Действие выполнено</small><b>Клиент записан · 16:30</b><span>Подтверждение отправлено</span></div></div>
    <div className="v4-stage-caption"><span>Обращение</span><ArrowRight/><span>Понимание</span><ArrowRight/><span>Действие</span></div>
  </div>
}

export function DelnoPage({version4=false}:{version4?:boolean}){
  const pageFeatures=version4?v4Features:features;
  const pageFaq=version4?v4Faq:faq;
  const pageChannels=version4?v4ClientChannels:clientChannels;
  return <main className={version4?"v2 v4-refined":"v2"}>
    <header className="v2-header">
      <Link className="v2-logo" href={version4?"/v4":"/"}><DelnoMark/>DELNO</Link>
      <ActiveNav />
      <div className="v2-header-right"><a className="voice-cta" href="#demo"><span className="voice-cta-orb"><Mic/></span><span>Спросить вслух</span></a></div>
    </header>

    <section className="v2-hero" id="product">
      <div className="v2-hero-copy">
        <div className="v2-status"><i/> {version4?"ИИ-сотрудник для бизнеса":"Единое окно для всех обращений"}</div>
        {version4?<h1>Ваш ИИ-сотрудник,<br/><span>который отвечает клиентам вместо вас.</span></h1>:<h1>Клиенты пишут<br/>и звонят.<br/><span>DELNO отвечает.</span></h1>}
        <p>{version4?"Принимает звонки, отвечает на сайте, в Telegram, MAX и по почте. Консультирует, принимает заявки и записывает клиентов — 24/7.":"DELNO принимает звонки и сообщения, отвечает по вашей базе знаний, записывает клиента и сохраняет результат. Вы подключаете только те каналы, которые нужны сейчас."}</p>
        {version4&&<><div className="hero-roles">Секретарь <i/> Администратор <i/> Оператор</div><p className="hero-one">Один сотрудник вместо секретаря, отдельных ботов и сервисов.</p></>}
        <div className="v2-actions">{version4?<><LeadFormTrigger className="v2-btn primary" label="Попробовать DELNO" source="Первый экран v4"/><a className="v2-btn secondary" href="#demo"><Play/> Посмотреть, как работает</a></>:<><a className="v2-btn primary" href="#demo">Попробовать голосом <ArrowRight/></a><a className="v2-btn secondary" href="#product"><Play/> Как это выглядит</a></>}</div>
      </div>
      <div className="hero-product">
      {version4?<V4ProductStage/>:<>
        <div className="hero-product-meta">
          <div className="hero-channels"><small>Отвечает там, где клиенту удобно</small><div>{pageChannels.map(({icon:Icon,label,tone,href,external})=><a className={tone} href={href} key={label} target={external?"_blank":undefined} rel={external?"noreferrer":undefined}><Icon/>{label}</a>)}</div></div>
          <div className="v2-note"><CircleCheck/> Запуск за несколько дней <span/> <CircleCheck/> Можно начать с одного канала {version4&&<><span/><CircleCheck/> Без программиста</>}</div>
        </div>
      {version4&&<div className="hero-flow"><span><Phone/>Клиент обращается</span><ArrowRight/><span><Sparkles/>DELNO отвечает</span><ArrowRight/><span><MessageCircle/>Консультирует</span><ArrowRight/><span><CalendarDays/>Записывает</span></div>}
      <div className="v2-console">
        <div className="console-bar"><div className="traffic"><i/><i/><i/></div><span>{version4?"dlno.ru":"app.delno.one"}</span><div className="console-avatar">Д</div></div>
        <div className="console-shell">
          <aside><div className="side-logo"><DelnoMark small/></div><button className="selected" aria-label="Диалоги"><MessageCircle/></button><button aria-label="Клиенты"><UserRound/></button><button aria-label="Календарь"><CalendarDays/></button><button aria-label="База знаний"><FileText/></button><div className="side-bottom"><button aria-label="Безопасность"><ShieldCheck/></button></div></aside>
          <section className="inbox">
            <div className="inbox-title"><div><small>Рабочее пространство</small><b>Диалоги</b></div><button><Search/></button></div>
            <div className="inbox-filter"><b>Все <span>12</span></b><span>Новые 4</span><span>Мои</span></div>
            <article className="hot"><div className="source phone"><Phone/></div><div><b>Анна Соколова</b><p>Хочу записаться на пятницу…</p></div><time>сейчас</time></article>
            <article><div className="source chat"><MessageCircle/></div><div><b>Михаил П.</b><p>Подскажите стоимость услуги</p></div><time>2 мин</time></article>
            <article><div className="source web"><Globe/></div><div><b>Новый посетитель</b><p>Вы работаете в выходные?</p></div><time>5 мин</time></article>
            <article><div className="source mail"><Mail/></div><div><b>ООО «Старт»</b><p>Запрос коммерческого предложения</p></div><time>12 мин</time></article>
          </section>
          <section className="conversation">
            <div className="person"><div><b>Анна Соколова</b><span>Входящий звонок · +7 921 ••• •• 18</span></div><div className="live-call"><i/> разговор завершён</div></div>
            <div className="timeline-label">Сегодня, 12:41</div>
            <div className="voice"><div className="voice-play"><Play/></div><div className="voice-wave">{Array.from({length:30}).map((_,i)=><i key={i}/>)}</div><span>2:14</span></div>
            <div className="delno-result">
              <div className="result-head"><span><Sparkles/> DELNO</span><small>Итог разговора</small></div>
              <p>Анна хочет записаться на консультацию в пятницу после 16:00. Уточнила стоимость и выбрала свободное окно.</p>
              <div className="result-tags"><span>Новый клиент</span><span>Запись</span><span>Консультация</span></div>
            </div>
            <div className="appointment"><div className="date"><b>29</b><span>авг</span></div><div><small>Запись создана</small><b>Консультация · 16:30</b><span>Анна Соколова · 60 минут</span></div><button><Check/></button></div>
            <div className="auto-note"><Zap/> Напоминание клиенту отправится автоматически</div>
          </section>
        </div>
        <div className="floating-metric metric-one"><span>Сегодня</span><b>27</b><small>обращений принято</small></div>
        <div className="floating-metric metric-two"><CircleCheck/><div><b>Клиент записан</b><span>Пятница, 16:30 · встреча в календаре</span></div></div>
      </div>
      </>}
      </div>
    </section>

    <section className="v2-section v2-promise">
      <div className="v2-kicker">Все каналы — один контекст</div>
      <div className="promise-grid"><h2>Не пять отдельных ботов.<br/><span>Один сотрудник.</span></h2><p>{version4?"Телефон, сайт, Telegram, MAX и почта работают через DELNO с общей базой знаний и едиными правилами. Все обращения собраны в одном рабочем пространстве.":"Не отдельный бот для сайта, второй для Telegram, третий для MAX и ещё один для звонков. DELNO отвечает во всех каналах из одной базы знаний и продолжает разговор с того места, где остановился клиент."}</p></div>
      <div className="channel-unifier"><div className="unifier-channels">{pageChannels.map(({icon:Icon,label,tone,href,external})=><a className={tone} href={href} key={label} target={external?"_blank":undefined} rel={external?"noreferrer":undefined}><i><Icon/></i><b>{label}</b></a>)}</div><div className="unifier-core"><DelnoMark small/><div><b>DELNO</b><span>{version4?"Одно рабочее пространство · одна база знаний":"Одна история клиента · одна база знаний"}</span></div></div></div>
      <div className="promise-stats"><article><b>24/7</b><span>может принимать обращения</span></article><article><b>1 окно</b><span>для всей истории клиента</span></article><article><b>1 база</b><span>знаний для всех каналов</span></article></div>
    </section>

    <VoiceDemo />

    <section className="brand-strip"><span>Телефон</span><i/><span>Сайт</span><i/><span>Telegram</span><i/><span>MAX</span><i/><span>Почта</span><i/><span>Календарь</span><i/><span>Одно окно</span></section>

    <section className="v2-features" id="solutions">
      <div className="feature-lead"><div className="v2-kicker">{version4?"Что можно поручить":"Что умеет"}</div><h2>{version4?<>Что DELNO делает<br/>вместо сотрудника.</>:<>Разговор<br/>продолжается.</>}</h2><p>{version4?"Отвечает, консультирует, записывает и звонит. Повторяющиеся обращения берёт на себя, а важные разговоры передаёт человеку.":"Клиент выбирает удобный канал. DELNO сохраняет контекст и ведёт его к следующему действию."}</p></div>
      <div className="feature-list">{pageFeatures.map(({icon:Icon,title,text,tag},i)=><article key={title} className={version4?`feature-bento feature-bento-${i}`:""}><span className="feature-index">0{i+1}</span><div className="feature-icon"><Icon/></div><div><small>{tag}</small><h3>{title}</h3><p>{text}</p></div>{version4?<div className={`feature-micro micro-${i}`}>{i===0?<><span>Клиент</span><p>Вы работаете в субботу?</p><b>Да, до 16:00.</b></>:i===1?<><span>Найдено в знаниях</span><b>Услуги и цены</b><small>Ответ подтверждён источником</small></>:i===2?<><span>Завтра</span><div><i>16:30</i><i>18:00</i></div><b><Check/> Время выбрано</b></>:<><span>Входящий звонок</span><div className="micro-wave">{Array.from({length:12}).map((_,n)=><i key={n}/>)}</div><b>02:14 · итог сохранён</b></>}</div>:<ChevronRight/>}</article>)}</div>
    </section>

    <section className="knowledge-v2">
      <div className="knowledge-demo">
        <div className="kb-head"><div><small>DELNO Кабинет</small><b>Знания</b></div><button>+ Добавить</button></div>
        {version4?<div className="v4-knowledge-flow"><div className="knowledge-sources"><span><Globe/>Сайт</span><span><FileText/>Прайс</span><span><MessageCircle/>FAQ</span><span><ShieldCheck/>Правила</span></div><div className="knowledge-core"><DelnoMark small/><b>DELNO</b><span>Находит точный ответ</span></div><div className="knowledge-answer"><small>Ответ клиенту</small><p>Да, по субботам работаем до 16:00.</p><span>Источник: Правила работы</span></div></div>:<><div className="kb-search"><Search/> Найти в базе знаний</div>
        <div className="kb-grid">
          <article><div className="kb-icon yellow">₽</div><b>Услуги и цены</b><span>42 позиции</span><small><i/> Актуально</small></article>
          <article><div className="kb-icon green">?</div><b>Частые вопросы</b><span>68 ответов</span><small><i/> Актуально</small></article>
          <article><div className="kb-icon blue">≡</div><b>Правила общения</b><span>12 сценариев</span><small><i/> Актуально</small></article>
          <article className="kb-add"><b>＋</b><span>Добавить источник</span></article>
        </div></>}
        <div className="kb-footer"><ShieldCheck/><div><b>Знания проверены</b><span>DELNO использует их во всех каналах</span></div><CircleCheck/></div>
      </div>
      <div className="knowledge-text"><div className="v2-kicker pale">{version4?"DELNO знает ваш бизнес":"Понимает ваш бизнес"}</div><h2>Расскажите один раз.<br/>DELNO запомнит.</h2><p>{version4?"Добавьте сайт, услуги, цены, документы и правила работы. DELNO использует эти знания во всех подключённых каналах.":"Добавьте прайс, список услуг, документы, ссылки и правила. Меняете информацию в одном месте — она обновляется сразу для звонков, чатов и писем."}</p><ul><li><Check/> Управление без программиста</li><li><Check/> Чёткие границы самостоятельности</li><li><Check/> Передача сложного вопроса человеку</li></ul></div>
    </section>

    <section className="v2-section launch"><div className="v2-kicker">Пошаговое подключение</div><div className="launch-grid"><div><h2>Начните<br/>с одной задачи.</h2><p>Выбираем участок, где DELNO быстрее всего принесёт пользу: ответы на сайте, запись клиентов или звонки. Настраиваем и проверяем его — после этого подключаем следующие каналы.</p><LeadFormTrigger className="v2-text-link lead-link" label="Обсудить первую задачу" source="Блок подключения" /></div><ol><li><span>01</span><div><b>Выбираем первую задачу</b><p>Фиксируем результат, который должен получить клиент и ваш бизнес.</p></div></li><li><span>02</span><div><b>Подключаем канал и знания</b><p>Сайт, телефон или мессенджер; услуги, цены и правила.</p></div></li><li><span>03</span><div><b>Проверяем реальные диалоги</b><p>Настраиваем тон, ответы и передачу сложных вопросов человеку.</p></div></li><li><span>04</span><div><b>Запускаем и расширяем</b><p>Следим за результатами и подключаем следующие каналы.</p></div></li></ol></div></section>

    {version4&&<section className="v2-section business-examples"><div className="v2-kicker">Как это выглядит для вашего бизнеса</div><div className="examples-head"><h2>Узнайте в этих диалогах<br/>своих клиентов.</h2><p>DELNO не просто отвечает. Он ведёт обращение к понятному результату: консультации, заявке или записи.</p></div><ScenarioSwitcher/><p className="future-note">Сегодня DELNO отвечает вашим клиентам. Завтра вы сможете поручать ему всё больше работы.</p></section>}

    <section className="v2-pricing" id="prices">
      <div className="v2-pricing-head"><div className="v2-kicker pale">{version4?"Два понятных способа начать":"Простые тарифы"}</div><h2>{version4?<>Выберите, как клиенты<br/>обращаются к вам.</>:<>Выберите, что<br/>нужно сейчас.</>}</h2><p>{version4?"«Диалоги» — сайт, мессенджеры и голосовой виджет без телефонного номера. «Диалоги + звонки» — когда нужны обычные входящие и исходящие телефонные разговоры.":"«Диалоги» — для сайта и мессенджеров. «Диалоги + звонки» — когда нужен телефон. Индивидуальный тариф — для нескольких точек и глубокой интеграции."}</p></div>
      <div className="price-logic"><div><b>Понятная абонентская плата</b><span>кабинет, база знаний, каналы и стартовый объём обращений</span></div><i/><div><b>Контроль дополнительных расходов</b><span>минуты и массовые отправки сверх пакета — только по фактическому объёму</span></div></div>
      <div className="v2-price-grid">
        <article>
          <span>Диалоги</span><h3>2 990 ₽<small>/ мес.</small></h3>
          {version4?<p>Для тех, кому клиенты пишут.</p>:<div className="price-fit"><b>Для кого</b><p>Специалист или небольшой бизнес, которому важно сразу отвечать клиентам онлайн.</p></div>}
          <ul><li><Check/> До 300 ИИ-диалогов в месяц</li><li><Check/> Чат на сайте</li><li className="channel-line"><Check/> Telegram, MAX и другие мессенджеры</li><li><Check/> Единая база знаний</li>{version4&&<><li><Check/> Голосовой виджет на сайте</li><li><Check/> 30 минут голоса в виджете</li></>}</ul>
          {!version4&&<div className="price-reason"><b>Почему 2 990 ₽</b><p>«Диалоги» — это текстовая работа на сайте и в мессенджерах, без телефонного номера и затрат на телефонию. В тариф уже входят база знаний, запись и стартовый объём обращений.</p></div>}
          <LeadFormTrigger className="price-lead" label={version4?"Попробовать":"Оставить заявку"} source="Тариф Диалоги — 2 990 ₽" />
        </article>
        <article className="best">
          <div className="best-label">Для большинства</div><span>Диалоги + звонки</span><h3>5 990 ₽<small>/ мес.</small></h3>
          {version4?<p>Для тех, кому клиенты ещё и звонят.</p>:<div className="price-fit"><b>Для кого</b><p>Бизнес, где звонок — важный источник записи, заказа или заявки.</p></div>}
          <ul><li><Check/> Всё из тарифа «Диалоги»</li><li><Check/> 100 минут телефонных разговоров</li><li><Check/> Входящие и исходящие звонки</li><li><Check/> Итог разговора и передача человеку</li></ul>
          {!version4&&<div className="price-reason"><b>Почему 5 990 ₽</b><p>Включены голосовой контур и первые 100 минут — можно проверить пользу без крупного внедрения.</p></div>}
          <LeadFormTrigger className="price-lead" label="Получить демо" source="Тариф Диалоги + звонки — 5 990 ₽" /><small className="price-foot">Сверх пакета — поминутно; телефония зависит от оператора</small>
        </article>
        <article>
          <span>Компания</span><h3>Индивидуально</h3>
          <div className="price-fit"><b>Для кого</b><p>Сеть, отдел продаж или компания с несколькими точками и системами.</p></div>
          <ul><li><Check/> Несколько номеров и филиалов</li><li><Check/> Роли для сотрудников</li><li><Check/> Интеграции с вашими системами</li><li><Check/> Индивидуальные сценарии и запуск</li></ul>
          <div className="price-reason"><b>Почему индивидуально</b><p>Стоимость зависит от количества точек, каналов и объёма интеграций.</p></div>
          <LeadFormTrigger className="price-lead" label="Рассчитать стоимость" source="Тариф Компания" />
        </article>
      </div>
    </section>

    <FaqSection fallback={pageFaq} version4={version4} />

    <section className="v2-final" id="contact"><div className="final-glow"/><div className="v2-logo giant-logo"><DelnoMark/>DELNO</div><h2>{version4?<>Покажем DELNO<br/>на вашем <span>бизнесе.</span></>:<>Давайте покажем,<br/>как DELNO будет работать <span>у вас.</span></>}</h2><p>{version4?"Без длинной презентации: выберем одно обращение клиента и покажем, как DELNO его обработает.":"Поговорите с помощником прямо на сайте, позвоните или напишите в удобный мессенджер — подготовим демо на примере вашего бизнеса."}</p><LeadFormTrigger className="v2-btn final-lead" label={version4?"Получить демо":"Оставить заявку"} source="Финальный экран" /><div className="contact-options"><a className="contact-voice" href="#demo"><span className="voice-cta-orb"><Mic/></span><span><b>Поговорить с DELNO</b><small>Голосовое демо на сайте</small></span></a><a className="contact-phone" href="tel:+78005550000"><Phone/><span><b>Позвонить</b><small>8 800 555-00-00</small></span></a><a className="contact-telegram" href={version4?"https://t.me/Dlno_bot":"https://t.me/quantumlabss"} target="_blank" rel="noreferrer"><Send/><span><b>Telegram</b><small>{version4?"@Dlno_bot":"@quantumlabss"}</small></span></a><a className="contact-max" href={version4?"https://max.ru/@id471405233378_bot":"https://max.ru/id7840118071_bot"} target="_blank" rel="noreferrer"><MessageCircle/><span><b>MAX</b><small>Открыть чат с ботом</small></span></a><a className="contact-mail" href={version4?"mailto:office@dlno.ru":"mailto:hello@delno.one?subject=Хочу%20демо%20DELNO"}><Mail/><span><b>Написать на почту</b><small>{version4?"office@dlno.ru":"hello@delno.one"}</small></span></a></div><small className="response-note">Выберите удобный способ — ответим в рабочее время</small></section>
    <footer className="v2-footer"><Link className="v2-logo" href={version4?"/v4":"/"}><DelnoMark/>DELNO</Link><p>ИИ-сотрудник для работы с клиентами.<br/>Отвечает дельно. Работает по делу.</p><div><a href="#solutions">Возможности</a><a href="#prices">Тарифы</a><a href="#answers">Вопросы</a><a href="tel:+78005550000">8 800 555-00-00</a><a href={version4?"https://t.me/Dlno_bot":"https://t.me/quantumlabss"} target="_blank" rel="noreferrer">Telegram</a><a href={version4?"https://max.ru/@id471405233378_bot":"https://max.ru/id7840118071_bot"} target="_blank" rel="noreferrer">MAX</a><a href={version4?"mailto:office@dlno.ru":"mailto:hello@delno.one"}>{version4?"office@dlno.ru":"hello@delno.one"}</a><Link href="/privacy">Конфиденциальность</Link><Link href="/terms">Пользовательское соглашение</Link></div><small>© 2026 DELNO</small></footer>
  </main>
}

export default function DelnoV2(){return <DelnoPage/>}
