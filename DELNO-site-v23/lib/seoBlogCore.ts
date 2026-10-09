/**
 * SEO-ядро блога DELNO (методика Вордstat: сиды → топы → кластеры).
 * Частоты (wsBase) заполняются после доступа к Wordstat/Direct API
 * или ручной выгрузки из https://wordstat.yandex.ru/ (регион: Россия, 225).
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

/** Кандидаты на новые статьи (после съёма частот — приоритизировать по wsBase). */
export const blogTopicBacklog: KeywordRow[] = [
  { phrase: "чат бот для салона красоты", wsBase: null, intent: "commercial" },
  { phrase: "чат бот для клиники", wsBase: null, intent: "commercial" },
  { phrase: "бот для записи на прием", wsBase: null, intent: "commercial" },
  { phrase: "голосовой бот для бизнеса", wsBase: null, intent: "commercial" },
  { phrase: "бот для приема звонков", wsBase: null, intent: "commercial" },
  { phrase: "ии администратор", wsBase: null, intent: "commercial" },
  { phrase: "нейросотрудник", wsBase: null, intent: "commercial" },
  { phrase: "автоматизация звонков", wsBase: null, intent: "commercial" },
];

export function getClusterForSlug(slug: string): BlogSeoCluster | undefined {
  return blogSeoClusters.find((c) => c.slug === slug);
}

/** Все уникальные фразы ядра (для пакетного съёма частот). */
export function allCorePhrases(): string[] {
  const set = new Set<string>();
  for (const seed of wordstatSeedQueue) set.add(seed);
  for (const c of blogSeoClusters) {
    set.add(c.primary.phrase);
    for (const k of [...c.secondary, ...c.lsi]) set.add(k.phrase);
  }
  for (const t of blogTopicBacklog) set.add(t.phrase);
  return [...set];
}
