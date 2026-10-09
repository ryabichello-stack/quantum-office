import type { LucideIcon } from "lucide-react";
import { Earth, Mail, Phone } from "lucide-react";

export type NeuralChannelId = "phone" | "telegram" | "max" | "mail";

export type NeuralChannel = {
  id: NeuralChannelId;
  name: string;
  color: string;
  Icon?: LucideIcon;
  business: string;
  customer: string;
  reply: string;
  result: string;
  detail: string;
  note: string;
};

export const neuralChannels: NeuralChannel[] = [
  {
    id: "phone",
    name: "Телефон",
    color: "#21a66b",
    Icon: Phone,
    business: "Автосервис",
    customer: "Здравствуйте! Запишите меня на замену масла завтра на 16:30, пожалуйста.",
    reply: "Да, есть 16:30. Записала вас на замену масла. Ждём завтра!",
    result: "Клиент записан",
    detail: "Завтра, 16:30 · замена масла",
    note: "Пример сценария. Запись — после подключения расписания.",
  },
  {
    id: "telegram",
    name: "Telegram",
    color: "#259ed8",
    business: "Салон красоты",
    customer: "Сколько стоит стрижка? И можно записаться на пятницу?",
    reply: "Стрижка — 2 500 ₽. В пятницу есть 18:00. Вам подойдёт?",
    result: "Время предложено",
    detail: "Пятница, 18:00 · стрижка",
    note: "Пример диалога. Цены и услуги — иллюстративные.",
  },
  {
    id: "max",
    name: "MAX",
    color: "#6855ed",
    business: "Клиника",
    customer: "Что взять с собой на первый приём?",
    reply:
      "Возьмите паспорт и результаты прошлых обследований, если они есть. Приходите за 15 минут до приёма — оформим документы.",
    result: "Клиент получил ответ",
    detail: "Администратору не пришлось отвлекаться",
    note: "Пример. Подключение MAX зависит от требований платформы.",
  },
  {
    id: "mail",
    name: "Почта",
    color: "#367aee",
    Icon: Mail,
    business: "Компания услуг",
    customer: "Добрый день! Работаете с юридическими лицами? Какие документы нужны?",
    reply:
      "Да, работаем по договору. Пришлите реквизиты и описание задачи — передам менеджеру для подготовки предложения.",
    result: "Запрос подготовлен для команды",
    detail: "Вместе с контекстом и данными клиента",
    note: "Пример сценария. Подключение почты уточним перед запуском.",
  },
];

export const outboundPhoneScenario = {
  business: "Салон красоты",
  customer: "Да, всё в силе. Буду вовремя!",
  reply: "Здравствуйте! Это ИИ-помощник салона. Вы записаны завтра в 15:00. Подтверждаете визит?",
  result: "Визит подтверждён",
  detail: "Завтра, 15:00 · клиент придёт",
  note: "Пример исходящего звонка по существующей записи.",
};

export const siteChannelPreview = {
  id: "site" as const,
  name: "Сайт",
  color: "#8561d8",
  Icon: Earth,
};
