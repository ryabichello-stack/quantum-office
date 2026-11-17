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
    reply: "Уточню возможность записи на завтра к 16:30 и передам запрос администратору.",
    result: "Заявка передана",
    detail: "Желаемое время: завтра, 16:30",
    note: "Иллюстрация сценария. Время подтверждает администратор или подключённая система записи.",
  },
  {
    id: "telegram",
    name: "Telegram",
    color: "#259ed8",
    business: "Салон красоты",
    customer: "Сколько стоит стрижка? И можно записаться на пятницу?",
    reply: "Стрижка стоит 2 500 ₽. Уточню, доступно ли время в пятницу, и передам ваш запрос.",
    result: "Запрос на запись принят",
    detail: "Желаемый день: пятница",
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
  result: "Ответ передан администратору",
  detail: "Клиент подтвердил намерение прийти",
  note: "Иллюстрация исходящего сценария для проверки в пилоте.",
};

export const siteChannelPreview = {
  id: "site" as const,
  name: "Сайт",
  color: "#8561d8",
  Icon: Earth,
};
