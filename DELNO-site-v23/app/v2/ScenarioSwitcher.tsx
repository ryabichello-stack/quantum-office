"use client";

import { CalendarDays, CircleCheck, MessageCircle, Scissors, Stethoscope, Wrench } from "lucide-react";
import { useState } from "react";

type Scenario = {
  id: string;
  label: string;
  icon: typeof Scissors;
  channel: string;
  channelIcon: typeof MessageCircle;
  lines: { who: "client" | "delno"; text: string; source?: string }[];
  resultTitle: string;
  resultText: string;
  resultFoot: string;
};

const scenarios: Scenario[] = [
  {
    id: "beauty",
    label: "Салон красоты",
    icon: Scissors,
    channel: "Telegram · сейчас",
    channelIcon: MessageCircle,
    lines: [
      { who: "client", text: "Можно записаться на окрашивание в субботу после 15:00?" },
      {
        who: "delno",
        text: "Да, в субботу свободны 15:30 и 17:00. Окрашивание занимает около 2,5 часов — какое время удобнее?",
        source: "Услуги и цены · расписание",
      },
      { who: "client", text: "15:30 подойдёт." },
      {
        who: "delno",
        text: "Записала вас на субботу в 15:30. Отправлю напоминание за день до визита.",
        source: "Календарь",
      },
    ],
    resultTitle: "Клиент записан на субботу",
    resultText: "Услуга, время и контакт сохранены в кабинете.",
    resultFoot: "Напоминание · 15:30 · мастер Ольга",
  },
  {
    id: "clinic",
    label: "Стоматология",
    icon: Stethoscope,
    channel: "Сайт · чат",
    channelIcon: MessageCircle,
    lines: [
      { who: "client", text: "Сколько стоит первичная консультация и можно ли сегодня вечером?" },
      {
        who: "delno",
        text: "Первичный осмотр — 1 500 ₽. Сегодня свободно в 18:40 и 19:20. Оставьте имя и телефон — подтвержу запись.",
        source: "Прайс · расписание",
      },
      { who: "client", text: "Иван, +7 921 ••• •• 44. На 19:20." },
      {
        who: "delno",
        text: "Запись на 19:20 создана. Пришлю SMS с адресом клиники и правилами подготовки.",
        source: "Правила приёма",
      },
    ],
    resultTitle: "Запись и цена подтверждены",
    resultText: "Клиент получил ответ без ожидания администратора.",
    resultFoot: "Консультация · 19:20 · каб. 2",
  },
  {
    id: "service",
    label: "Сервисный центр",
    icon: Wrench,
    channel: "Входящий звонок",
    channelIcon: MessageCircle,
    lines: [
      { who: "client", text: "Ноутбук не включается после обновления. Можно сегодня сдать на диагностику?" },
      {
        who: "delno",
        text: "Да, диагностика бесплатна при ремонте. Сегодня примем до 20:00 на ул. Ленина, 12. Нужен номер заявки для очереди?",
        source: "FAQ · адреса",
      },
      { who: "client", text: "Да, запишите, приеду через час." },
      {
        who: "delno",
        text: "Заявка №1842. Ожидаем вас до 20:00, инженер получит описание проблемы заранее.",
        source: "CRM · очередь",
      },
    ],
    resultTitle: "Заявка принята по телефону",
    resultText: "Итог разговора и номер очереди переданы мастеру.",
    resultFoot: "Диагностика · заявка №1842",
  },
];

export default function ScenarioSwitcher() {
  const [active, setActive] = useState(scenarios[0].id);
  const scenario = scenarios.find((s) => s.id === active) ?? scenarios[0];
  const ChannelIcon = scenario.channelIcon;

  return (
    <div className="scenario-switcher">
      <div className="scenario-tabs" role="tablist" aria-label="Примеры диалогов по отраслям">
        {scenarios.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={active === id}
            onClick={() => setActive(id)}
          >
            <Icon aria-hidden />
            {label}
          </button>
        ))}
      </div>
      <div className="scenario-stage" role="tabpanel">
        <div className="scenario-dialog">
          <div className="scenario-channel">
            <ChannelIcon aria-hidden />
            {scenario.channel}
            <i aria-hidden />
          </div>
          {scenario.lines.map((line, index) => (
            <div key={index} className={`scenario-bubble ${line.who}`}>
              <small>{line.who === "client" ? "Клиент" : "DELNO"}</small>
              <p>{line.text}</p>
              {line.source ? <span>Источник: {line.source}</span> : null}
            </div>
          ))}
        </div>
        <div className="scenario-result">
          <div className="scenario-check">
            <CircleCheck aria-hidden />
          </div>
          <small>Результат для бизнеса</small>
          <h3>{scenario.resultTitle}</h3>
          <p>{scenario.resultText}</p>
          <div>
            <CalendarDays aria-hidden />
            {scenario.resultFoot}
          </div>
        </div>
      </div>
    </div>
  );
}
