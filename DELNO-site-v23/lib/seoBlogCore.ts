/**
 * SEO-ядро блога DELNO (методика Вордstat: сиды → топы → кластеры).
 * Частоты (wsBase) заполняются после доступа к Wordstat/Direct API
 * или ручной выгрузки из https://wordstat.yandex.ru/ (регион: Россия, 225).
 *
 * Публичный контент: только бренд DELNO. Внутренние имена (AVA и т.п.) не использовать.
 *
 * Статус API на 2026-10-09:
 * - OAuth: wordstat:api + marketing token OK
 * - api.wordstat.yandex.net: TLS/404 (доступ не активирован)
 * - Direct KeywordsResearch: error 58 — «заявка на доступ в интерфейсе Директа»
 */

export type WsFreq = number | null;

export type KeywordRow = {
  phrase: string;
  /** Базовая частотность Вордstat за 30 дней (Россия), null = ещё не снято */
  wsBase: WsFreq;
  intent: "informational" | "commercial" | "transactional" | "navigational";
  notes?: string;
};

export type BlogSeoCluster = {
  /** slug статьи в /blog/[slug] */
  slug: string;
  /** Главный запрос (title / H1) */
  primary: KeywordRow;
  /** Сильные вторичные */
  secondary: KeywordRow[];
  /** LSI / смежные из топа Вордstat */
  lsi: KeywordRow[];
  /** Рекомендуемый title (≤ ~70 символов) */
  metaTitle: string;
  /** Meta description */
  metaDescription: string;
  /** Минус-смыслы (не тащим в статью) */
  minus: string[];
};

/** Сиды для массового съёма в Вордstat / API (порядок = приоритет). */
export const wordstatSeedQueue: string[] = [
  // ядро продукта
  "ии сотрудник",
  "нейросотрудник",
  "ии администратор",
  "голосовой бот",
  "голосовой помощник для бизнеса",
  "бот для приема звонков",
  "автоматизация звонков",
  "чат бот для сайта",
  "чат бот telegram",
  "бот для записи клиентов",
  "бот для записи на прием",
  // сценарии / контент
  "база знаний для бота",
  "как настроить чат бот",
  "единый бот для всех каналов",
  "бот вместо администратора",
  "чат бот для салона красоты",
  "чат бот для клиники",
  "голосовой бот для бизнеса",
  "автоответчик с ии",
  "бот для бизнеса",
];

/**
 * Кластеры → статьи блога.
 * Частоты wsBase = null до выгрузки Вордstat; структура готова к заполнению.
 */
export const blogSeoClusters: BlogSeoCluster[] = [
  {
    slug: "one-employee-many-channels",
    primary: {
      phrase: "ии сотрудник",
      wsBase: null,
      intent: "commercial",
      notes: "Главный бренд/категорийный запрос DELNO",
    },
    secondary: [
      { phrase: "нейросотрудник", wsBase: null, intent: "commercial" },
      { phrase: "единый бот для всех каналов", wsBase: null, intent: "informational" },
      { phrase: "бот вместо администратора", wsBase: null, intent: "commercial" },
      { phrase: "чат бот telegram", wsBase: null, intent: "commercial" },
    ],
    lsi: [
      { phrase: "ии администратор", wsBase: null, intent: "commercial" },
      { phrase: "бот для бизнеса", wsBase: null, intent: "commercial" },
      { phrase: "один бот для звонков и чатов", wsBase: null, intent: "informational" },
      { phrase: "омниканальный бот", wsBase: null, intent: "informational" },
    ],
    metaTitle: "ИИ-сотрудник вместо нескольких ботов — один для всех каналов",
    metaDescription:
      "Зачем бизнесу один ИИ-сотрудник вместо чат-бота, автоответчика и скриптов: общая база знаний, Telegram, звонки и сайт в одной истории обращения.",
    minus: ["фриланс", "вакансия", "работа ии", "курсы", "обучение нейросетям"],
  },
  {
    slug: "prepare-knowledge-base",
    primary: {
      phrase: "база знаний для бота",
      wsBase: null,
      intent: "informational",
    },
    secondary: [
      { phrase: "как настроить чат бот", wsBase: null, intent: "informational" },
      { phrase: "чат бот для сайта", wsBase: null, intent: "commercial" },
      { phrase: "бот для записи клиентов", wsBase: null, intent: "commercial" },
    ],
    lsi: [
      { phrase: "скрипт для бота", wsBase: null, intent: "informational" },
      { phrase: "что загрузить в базу знаний", wsBase: null, intent: "informational" },
      { phrase: "прайс для чат бота", wsBase: null, intent: "informational" },
      { phrase: "первый сценарий бота", wsBase: null, intent: "informational" },
    ],
    metaTitle: "База знаний для бота: что подготовить перед запуском",
    metaDescription:
      "Чек-лист материалов для ИИ-сотрудника: сайт, прайс, услуги, правила записи. Как проверить ответы до телефонии и не усложнять старт.",
    minus: ["виртуальная машина", "конfluence", "sharepoint", "википедия"],
  },
  {
    slug: "voice-and-chat-one-policy",
    primary: {
      phrase: "голосовой бот",
      wsBase: null,
      intent: "commercial",
    },
    secondary: [
      { phrase: "голосовой помощник для бизнеса", wsBase: null, intent: "commercial" },
      { phrase: "бот для приема звонков", wsBase: null, intent: "commercial" },
      { phrase: "автоматизация звонков", wsBase: null, intent: "commercial" },
      { phrase: "автоответчик с ии", wsBase: null, intent: "commercial" },
    ],
    lsi: [
      { phrase: "голосовой бот для бизнеса", wsBase: null, intent: "commercial" },
      { phrase: "ии для звонков", wsBase: null, intent: "commercial" },
      { phrase: "чат и голос один сценарий", wsBase: null, intent: "informational" },
      { phrase: "скрипт оператора и бота", wsBase: null, intent: "informational" },
    ],
    metaTitle: "Голосовой бот и чат по одним правилам — без расхождений",
    metaDescription:
      "Почему голос и мессенджеры должны жить на одной базе знаний: одинаковые цены, эскалации и запись клиента в звонке и в виджете.",
    minus: ["алиса колонка", "siri", "google assistant домашний", "умный дом"],
  },
  {
    slug: "launch-checklist",
    primary: {
      phrase: "как запустить чат бот",
      wsBase: null,
      intent: "informational",
    },
    secondary: [
      { phrase: "чат бот для салона красоты", wsBase: null, intent: "commercial" },
      { phrase: "чат бот для клиники", wsBase: null, intent: "commercial" },
      { phrase: "бот для записи на прием", wsBase: null, intent: "commercial" },
    ],
    lsi: [
      { phrase: "проверить бота перед запуском", wsBase: null, intent: "informational" },
      { phrase: "тестовые фразы для бота", wsBase: null, intent: "informational" },
      { phrase: "эскалация на оператора", wsBase: null, intent: "informational" },
      { phrase: "интеграция бота с crm", wsBase: null, intent: "commercial" },
    ],
    metaTitle: "Чек-лист запуска ИИ-бота: от тестовых фраз до прода",
    metaDescription:
      "Пять шагов перед включением ИИ-сотрудника: типовые вопросы, отказы, запись в CRM, тон бренда и контроль диалогов первые недели.",
    minus: ["разработка бота с нуля", "python telegram bot tutorial", "код бота"],
  },
];

/** Доп. сиды под серию «ИИ в бизнесе + ниши» (см. docs/DELNO_BLOG_SERIES_PLAN.md). */
export const blogSeriesSeeds: string[] = [
  "как внедрить ии в бизнес",
  "ии для малого бизнеса",
  "ии сотрудник для бизнеса",
  "запись на маникюр бот",
  "бот для барбершопа",
  "бот для записи на тренировку",
  "бот для автосервиса",
  "запись на шиномонтаж",
  "бот для записи на фотосессию",
  "запись к врачу бот",
  "бот для записи на массаж",
  "бот для автошколы",
  "бот для записи к репетитору",
  "бот для ветклиники",
  "напоминание о записи",
  "подтверждение записи",
  "перенос записи бот",
  "стоимость чат бота",
  "бот вместо администратора",
  "голосовой бот для бизнеса",
  "конструктор чат ботов",
];

export type SeriesPillar = "A" | "B" | "C" | "D" | "E";

export type SeriesArticlePlan = {
  id: string;
  pillar: SeriesPillar;
  slug: string;
  title: string;
  primary: string;
  seeds: string[];
  /** Product capabilities to feature (honest scope). */
  features: string[];
  wave: 1 | 2 | 3;
  status: "live" | "planned";
};

/**
 * Полная серия ~36 статей: внедрение ИИ → каналы → ниши → запуск → деньги.
 * Живые 4 статьи помечены status: live (существующие slug).
 */
export const blogSeriesPlan: SeriesArticlePlan[] = [
  // A — внедрение
  {
    id: "A01",
    pillar: "A",
    slug: "one-employee-many-channels",
    title: "ИИ-сотрудник вместо нескольких ботов",
    primary: "ии сотрудник",
    seeds: ["нейросотрудник", "единый бот для всех каналов", "бот вместо администратора"],
    features: ["omnichannel", "kb", "telegram", "site", "phone"],
    wave: 1,
    status: "live",
  },
  {
    id: "A02",
    pillar: "A",
    slug: "start-with-one-task",
    title: "Внедрить ИИ просто: одна задача, один канал, без IT-отдела",
    primary: "как внедрить ии в бизнес",
    seeds: ["как запустить чат бот", "первый сценарий бота"],
    features: ["pilot", "one-channel", "simple-fast-cheap"],
    wave: 1,
    status: "planned",
  },
  {
    id: "A03",
    pillar: "A",
    slug: "cheap-employee-24-7",
    title: "Недорого и по делу: ИИ-сотрудник от 2 990 ₽ вместо вечной трубы",
    primary: "ии администратор",
    seeds: ["бот вместо администратора", "стоимость чат бота", "ии сотрудник для бизнеса"],
    features: ["pricing", "site", "telegram", "max", "simple-fast-cheap"],
    wave: 1,
    status: "planned",
  },
  {
    id: "A04",
    pillar: "A",
    slug: "prepare-knowledge-base",
    title: "База знаний — это и есть продукт",
    primary: "база знаний для бота",
    seeds: ["как настроить чат бот", "прайс для чат бота"],
    features: ["kb"],
    wave: 1,
    status: "live",
  },
  {
    id: "A05",
    pillar: "A",
    slug: "where-ai-fails",
    title: "Где ИИ обязан молчать и звать человека",
    primary: "эскалация на оператора",
    seeds: ["передача обращения человеку"],
    features: ["escalation"],
    wave: 2,
    status: "planned",
  },
  {
    id: "A06",
    pillar: "A",
    slug: "ai-for-small-business-russia",
    title: "ИИ для малого бизнеса в РФ: Telegram, MAX и телефон",
    primary: "ии для малого бизнеса",
    seeds: ["ии сотрудник для бизнеса"],
    features: ["telegram", "max", "phone", "site"],
    wave: 2,
    status: "planned",
  },
  {
    id: "A07",
    pillar: "A",
    slug: "from-demo-to-first-week",
    title: "От демо на сайте до первой рабочей недели",
    primary: "как запустить чат бот",
    seeds: ["как внедрить ии в бизнес"],
    features: ["demo", "pilot"],
    wave: 2,
    status: "planned",
  },
  {
    id: "A08",
    pillar: "A",
    slug: "myths-about-ai-bots",
    title: "7 мифов про ИИ-ботов для бизнеса",
    primary: "нейросотрудник",
    seeds: ["ии сотрудник"],
    features: ["kb", "escalation", "pricing"],
    wave: 2,
    status: "planned",
  },
  // B — каналы
  {
    id: "B01",
    pillar: "B",
    slug: "website-widget-that-answers",
    title: "Виджет на сайте, который отвечает по вашим ценам",
    primary: "чат бот для сайта",
    seeds: ["чат бот для сайта"],
    features: ["site-widget"],
    wave: 1,
    status: "planned",
  },
  {
    id: "B02",
    pillar: "B",
    slug: "voice-and-chat-one-policy",
    title: "Голос и чат по одним правилам",
    primary: "голосовой бот",
    seeds: ["голосовой помощник для бизнеса", "автоответчик с ии"],
    features: ["voice-widget", "kb"],
    wave: 1,
    status: "live",
  },
  {
    id: "B03",
    pillar: "B",
    slug: "telegram-bot-booking",
    title: "Telegram-бот для записи: сценарий, который не бесит",
    primary: "чат бот telegram",
    seeds: ["бот для записи клиентов", "бот для записи на прием"],
    features: ["telegram", "booking"],
    wave: 1,
    status: "planned",
  },
  {
    id: "B04",
    pillar: "B",
    slug: "max-messenger-for-business",
    title: "MAX для бизнеса рядом с Telegram",
    primary: "бот max",
    seeds: ["мессенджер max для бизнеса"],
    features: ["max"],
    wave: 2,
    status: "planned",
  },
  {
    id: "B05",
    pillar: "B",
    slug: "email-as-channel",
    title: "Почта как канал первой линии",
    primary: "бот для почты",
    seeds: ["автоответы на почту"],
    features: ["mail"],
    wave: 3,
    status: "planned",
  },
  {
    id: "B06",
    pillar: "B",
    slug: "phone-ai-incoming",
    title: "ИИ на входящих звонках: когда нужен тариф со звонками",
    primary: "бот для приема звонков",
    seeds: ["автоматизация звонков", "голосовой бот для бизнеса"],
    features: ["phone", "pricing-calls"],
    wave: 1,
    status: "planned",
  },
  {
    id: "B07",
    pillar: "B",
    slug: "reminders-reduce-no-shows",
    title: "Подтверждение накануне и перенос: как ИИ режет неявки",
    primary: "подтверждение записи",
    seeds: ["напоминание о записи", "перенос записи бот"],
    features: ["reminders", "confirm", "reschedule", "outbound"],
    wave: 2,
    status: "planned",
  },
  {
    id: "B08",
    pillar: "B",
    slug: "one-history-all-channels",
    title: "Одна история обращения во всех каналах",
    primary: "единый бот для всех каналов",
    seeds: ["омниканальный бот"],
    features: ["omnichannel"],
    wave: 2,
    status: "planned",
  },
  // C — ниши
  {
    id: "C01",
    pillar: "C",
    slug: "booking-manicure",
  {
    id: "C01",
    pillar: "C",
    slug: "booking-manicure",
    title: "Салон красоты: запись, перенос и подтверждение накануне",
    primary: "чат бот для салона красоты",
    seeds: ["запись на маникюр бот", "бот для записи клиентов", "подтверждение записи", "перенос записи бот"],
    features: ["telegram", "site", "booking", "reschedule", "confirm", "reminders", "simple-fast-cheap"],
    wave: 1,
    status: "planned",
  },
  {
    id: "C02",
    pillar: "C",
    slug: "booking-hairdresser",
    title: "Барбершоп: запись, перенос и подтверждение накануне",
    primary: "бот для барбершопа",
    seeds: ["чат бот для салона красоты", "подтверждение записи", "перенос записи бот"],
    features: ["telegram", "phone", "booking", "reschedule", "confirm", "reminders", "simple-fast-cheap"],
    wave: 1,
    status: "planned",
  },
  {
    id: "C03",
    pillar: "C",
    slug: "booking-fitness",
    title: "Фитнес и тренировки: запись, перенос и подтверждение накануне",
    primary: "бот для записи на тренировку",
    seeds: ["бот для фитнеса", "подтверждение записи", "напоминание о записи"],
    features: ["telegram", "booking", "reschedule", "confirm", "reminders", "simple-fast-cheap"],
    wave: 1,
    status: "planned",
  },
  {
    id: "C04",
    pillar: "C",
    slug: "booking-tire-service",
    title: "Шиномонтаж и автосервис: запись, перенос и подтверждение накануне",
    primary: "бот для автосервиса",
    seeds: ["запись на шиномонтаж", "бот для приема звонков", "подтверждение записи"],
    features: ["phone", "telegram", "booking", "reschedule", "confirm", "reminders", "simple-fast-cheap"],
    wave: 1,
    status: "planned",
  },
  {
    id: "C05",
    pillar: "C",
    slug: "booking-photo",
    title: "Фотостудия: запись, перенос и подтверждение накануне",
    primary: "бот для записи на фотосессию",
    seeds: ["бот для фотостудии", "подтверждение записи", "перенос записи бот"],
    features: ["site", "telegram", "booking", "reschedule", "confirm", "reminders", "simple-fast-cheap"],
    wave: 2,
    status: "planned",
  },
  {
    id: "C06",
    pillar: "C",
    slug: "booking-clinic",
    title: "Клиника: запись, перенос и подтверждение накануне (без медсоветов)",
    primary: "чат бот для клиники",
    seeds: ["запись к врачу бот", "подтверждение записи", "напоминание о записи"],
    features: ["telegram", "reminders", "escalation", "booking", "reschedule", "confirm", "simple-fast-cheap"],
    wave: 1,
    status: "planned",
  },
  {
    id: "C07",
    pillar: "C",
    slug: "booking-massage",
    title: "Массаж и SPA: запись, перенос и подтверждение накануне",
    primary: "бот для записи на массаж",
    seeds: ["бот для записи клиентов", "подтверждение записи"],
    features: ["telegram", "booking", "reschedule", "confirm", "reminders", "simple-fast-cheap"],
    wave: 2,
    status: "planned",
  },
  {
    id: "C08",
    pillar: "C",
    slug: "booking-auto-school",
    title: "Автошкола: запись, перенос и подтверждение занятия",
    primary: "бот для автошколы",
    seeds: ["бот для записи клиентов", "подтверждение записи"],
    features: ["site", "telegram", "mail", "booking", "reschedule", "confirm", "simple-fast-cheap"],
    wave: 3,
    status: "planned",
  },
  {
    id: "C09",
    pillar: "C",
    slug: "booking-tutor",
    title: "Репетитор и курсы: запись, перенос и подтверждение урока",
    primary: "бот для записи к репетитору",
    seeds: ["бот для онлайн школы", "перенос записи бот"],
    features: ["telegram", "mail", "booking", "reschedule", "confirm", "simple-fast-cheap"],
    wave: 3,
    status: "planned",
  },
  {
    id: "C10",
    pillar: "C",
    slug: "booking-vet",
    title: "Ветклиника: запись, перенос и подтверждение накануне",
    primary: "бот для ветклиники",
    seeds: ["чат бот для клиники", "подтверждение записи"],
    features: ["telegram", "phone", "booking", "reschedule", "confirm", "escalation", "simple-fast-cheap"],
    wave: 2,
    status: "planned",
  },
  {
    id: "C11",
    pillar: "C",
    slug: "booking-coworking",
    title: "Коворкинг: бронь, перенос и подтверждение переговорки",
    primary: "бот для бронирования переговорки",
    seeds: ["чат бот для сайта", "подтверждение записи"],
    features: ["site", "booking", "reschedule", "confirm", "simple-fast-cheap"],
    wave: 3,
    status: "planned",
  },
  {
    id: "C12",
    pillar: "C",
    slug: "booking-any-service",
    title: "Любой бизнес по записи: записал, перенёс, подтвердил накануне",
    primary: "бот для записи клиентов",
    seeds: ["бот для записи на прием", "подтверждение записи", "перенос записи бот", "напоминание о записи"],
    features: ["telegram", "site", "booking", "reschedule", "confirm", "reminders", "kb", "simple-fast-cheap"],
    wave: 1,
    status: "planned",
  },
  // D — запуск
  {
    id: "D01",
    pillar: "D",
    slug: "what-to-put-in-kb",
    title: "Что положить в базу знаний за один вечер",
    primary: "база знаний для бота",
    seeds: ["что загрузить в базу знаний"],
    features: ["kb"],
    wave: 1,
    status: "planned",
  },
  {
    id: "D02",
    pillar: "D",
    slug: "launch-checklist",
    title: "Чек-лист перед включением на прод",
    primary: "как запустить чат бот",
    seeds: ["тестовые фразы для бота"],
    features: ["pilot", "escalation", "booking"],
    wave: 1,
    status: "live",
  },
  {
    id: "D03",
    pillar: "D",
    slug: "calendar-without-double-booking",
    title: "Запись без двойных слотов",
    primary: "бот для записи на прием",
    seeds: ["бот для записи клиентов"],
    features: ["booking", "calendar"],
    wave: 2,
    status: "planned",
  },
  {
    id: "D04",
    pillar: "D",
    slug: "handoff-to-human",
    title: "Передача человеку: когда и с каким резюме",
    primary: "эскалация на оператора",
    seeds: ["передача обращения человеку"],
    features: ["escalation"],
    wave: 2,
    status: "planned",
  },
  {
    id: "D05",
    pillar: "D",
    slug: "week-1-control",
    title: "Первая неделя: что смотреть в диалогах",
    primary: "как запустить чат бот",
    seeds: ["контроль качества бота"],
    features: ["pilot"],
    wave: 2,
    status: "planned",
  },
  {
    id: "D06",
    pillar: "D",
    slug: "scale-channels-after-pilot",
    title: "Как наращивать каналы после пилота",
    primary: "единый бот для всех каналов",
    seeds: ["подключить telegram к сайту"],
    features: ["omnichannel", "telegram", "phone"],
    wave: 3,
    status: "planned",
  },
  // E — деньги / выбор
  {
    id: "E01",
    pillar: "E",
    slug: "price-2990-vs-admin",
    title: "2 990 ₽ vs администратор: почему малому бизнесу это по карману",
    primary: "стоимость чат бота",
    seeds: ["ии сотрудник для бизнеса", "бот вместо администратора"],
    features: ["pricing", "simple-fast-cheap"],
    wave: 1,
    status: "planned",
  },
  {
    id: "E02",
    pillar: "E",
    slug: "diy-bot-vs-delno",
    title: "Конструктор ботов vs готовый ИИ-сотрудник",
    primary: "конструктор чат ботов",
    seeds: ["чат бот для бизнеса"],
    features: ["kb", "omnichannel", "pricing"],
    wave: 2,
    status: "planned",
  },
  {
    id: "E03",
    pillar: "E",
    slug: "when-you-need-calls",
    title: "Когда хватит мессенджеров, а когда нужны звонки",
    primary: "голосовой бот для бизнеса",
    seeds: ["бот для приема звонков"],
    features: ["phone", "pricing-calls", "voice-widget"],
    wave: 2,
    status: "planned",
  },
  {
    id: "E04",
    pillar: "E",
    slug: "checklist-buy-ai-employee",
    title: "Чек-лист покупки ИИ-сотрудника",
    primary: "ии сотрудник для бизнеса",
    seeds: ["ии сотрудник"],
    features: ["pricing", "kb", "escalation", "pilot"],
    wave: 3,
    status: "planned",
  },
];

/** Кандидаты на новые статьи (после съёма частот — приоритизировать по wsBase). */
export const blogTopicBacklog: KeywordRow[] = blogSeriesPlan
  .filter((a) => a.status === "planned")
  .map((a) => ({
    phrase: a.primary,
    wsBase: null as WsFreq,
    intent: "commercial" as const,
    notes: `${a.id} · ${a.slug}`,
  }));

export function getClusterForSlug(slug: string): BlogSeoCluster | undefined {
  return blogSeoClusters.find((c) => c.slug === slug);
}

export function getSeriesArticle(slug: string): SeriesArticlePlan | undefined {
  return blogSeriesPlan.find((a) => a.slug === slug);
}

/** Все уникальные фразы ядра (для пакетного съёма частот). */
export function allCorePhrases(): string[] {
  const set = new Set<string>();
  for (const seed of wordstatSeedQueue) set.add(seed);
  for (const seed of blogSeriesSeeds) set.add(seed);
  for (const c of blogSeoClusters) {
    set.add(c.primary.phrase);
    for (const k of [...c.secondary, ...c.lsi]) set.add(k.phrase);
  }
  for (const a of blogSeriesPlan) {
    set.add(a.primary);
    for (const s of a.seeds) set.add(s);
  }
  return [...set];
}
