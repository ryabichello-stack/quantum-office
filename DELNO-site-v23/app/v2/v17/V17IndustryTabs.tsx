"use client";

import { ArrowRight, Check, PhoneOutgoing, Play } from "lucide-react";
import Image from "next/image";
import { useState } from "react";
import { LeadFormTrigger } from "../SiteControls";

type IndustryId = "beauty" | "clinic" | "auto";

const industries: {
  id: IndustryId;
  label: string;
  title: string;
  body: string;
  delnoLine: string;
  clientLine: string;
  outcome: string;
}[] = [
  {
    id: "beauty",
    label: "Салон красоты",
    title: "Администратор занят.\nЗаписи подтверждаются.",
    body: "DELNO звонит по списку записей, уточняет планы клиента и сохраняет ответ для администратора.",
    delnoLine: "Здравствуйте! Это ИИ-помощник салона. Вы записаны завтра на 15:00. Подтверждаете визит?",
    clientLine: "Да, буду. Спасибо!",
    outcome: "Визит подтверждён",
  },
  {
    id: "clinic",
    label: "Клиника",
    title: "Первый визит.\nОтветы без очереди.",
    body: "DELNO отвечает на типовые вопросы о подготовке, ценах и записи — в мессенджере или по телефону.",
    delnoLine: "Возьмите паспорт и результаты прошлых обследований, если они есть. Приходите за 15 минут до приёма.",
    clientLine: "Что взять с собой на первый приём?",
    outcome: "Клиент получил ответ",
  },
  {
    id: "auto",
    label: "Автосалон",
    title: "Заявка с сайта.\nБез потерянных лидов.",
    body: "DELNO уточняет интерес клиента, время визита и контакт — и передаёт менеджеру готовую заявку.",
    delnoLine: "Конечно. Подскажите удобное время и номер телефона — менеджер согласует встречу.",
    clientLine: "Хочу посмотреть автомобиль вживую. Можно приехать завтра?",
    outcome: "Посетитель переходит к записи",
  },
];

export default function V17IndustryTabs() {
  const [active, setActive] = useState<IndustryId>("beauty");
  const item = industries.find((i) => i.id === active)!;

  return (
    <div className="dv17-industry-tabs">
      <div className="dv17-segmented" role="tablist" aria-label="Примеры для вашей сферы">
        {industries.map((ind) => (
          <button
            key={ind.id}
            type="button"
            role="tab"
            aria-selected={active === ind.id}
            data-state={active === ind.id ? "active" : "inactive"}
            onClick={() => setActive(ind.id)}
          >
            {ind.label}
          </button>
        ))}
      </div>
      <div className="dv17-industry-panel" role="tabpanel">
        <div className="dv17-industry-copy">
          <span className="dv17-task-label">
            <PhoneOutgoing size={16} aria-hidden />
            Подтвердить запись
          </span>
          <h3>
            {item.title.split("\n").map((line, i) => (
              <span key={line}>
                {i > 0 && <br />}
                {line}
              </span>
            ))}
          </h3>
          <p>{item.body}</p>
          <LeadFormTrigger
            className="dv17-inline-link"
            label="Хочу так же"
            source="V17 industry scenario"
          />
        </div>
        <div className="dv17-industry-conversation">
          <div className="dv17-conversation-header">
            <Image src="/delno-mark.svg" alt="" width={22} height={21} />
            <strong>DELNO</strong>
            <span>Пример звонка</span>
          </div>
          <div className="dv17-dialog-line">
            <small>DELNO</small>
            <p>{item.delnoLine}</p>
          </div>
          <div className="dv17-dialog-line dv17-customer-line">
            <small>Клиент</small>
            <p>{item.clientLine}</p>
          </div>
          <div className="dv17-industry-outcome">
            <Check size={17} aria-hidden />
            {item.outcome}
          </div>
          <div className="dv17-sample-audio">
            <div>
              <button className="dv17-audio-button" type="button" aria-label="Послушать реплику DELNO">
                <Play size={18} aria-hidden />
              </button>
              <span className="dv17-wave" aria-hidden>
                {Array.from({ length: 32 }).map((_, i) => (
                  <i key={i} style={{ height: `${8 + (i % 5) * 5}px`, animationDelay: `${-(i % 8) * 0.13}s` }} />
                ))}
              </span>
              <span>Послушать реплику</span>
            </div>
            <small>Синтезированный голос · пример сценария</small>
          </div>
        </div>
      </div>
    </div>
  );
}
