"use client";

import { ArrowRight, Mic, Phone } from "lucide-react";
import { LeadFormTrigger } from "./SiteControls";

/** Trust strip — reduces bounce, answers “is this real?” in 3 seconds. */
export function ConvertTrustBar() {
  return (
    <div className="convert-trust" aria-label="Ключевые факты">
      <ul>
        <li>
          <strong>300</strong>
          <span>обращений в базовом пакете</span>
        </li>
        <li>
          <strong>24/7</strong>
          <span>ответы на сайте и в чатах</span>
        </li>
        <li>
          <strong>2 990 ₽</strong>
          <span>старт без телефонии</span>
        </li>
        <li>
          <strong>5 990 ₽</strong>
          <span>+ 100 мин звонков</span>
        </li>
      </ul>
    </div>
  );
}

/** Mobile sticky CTA — primary conversion path always visible. */
export function StickyMobileCTA() {
  return (
    <div className="convert-sticky-cta" aria-hidden={false}>
      <a className="convert-sticky-voice" href="#demo">
        <Mic aria-hidden />
        <span>Спросить вслух</span>
      </a>
      <LeadFormTrigger
        className="convert-sticky-lead"
        label="Демо на моём бизнесе"
        source="Sticky mobile CTA v2-convert"
      />
    </div>
  );
}

export function ConvertHeroExtras() {
  return (
    <div className="convert-hero-proof">
      <p>
        Попробуйте <a href="#demo">голосовое демо</a> на этой странице — тот же помощник, что
        поставим на ваш сайт. Без карты и без установки.
      </p>
      <div className="convert-hero-chips">
        <span>Голос cedar</span>
        <span>База знаний</span>
        <span>Telegram · MAX</span>
        <a href="tel:+78005550000">
          <Phone aria-hidden />
          8 800 555-00-00
        </a>
      </div>
    </div>
  );
}

export function ConvertPricingNote() {
  return (
    <div className="convert-limits-callout" id="limits">
      <div>
        <b>Сколько обращений входит?</b>
        <p>
          <strong>300 ИИ-диалогов</strong> в месяц на обоих тарифах. Сообщения внутри одного
          разговора не считаются поштучно. Голос на сайте — <strong>30 мин/мес</strong>, телефон —
          <strong> 100 мин/мес</strong> на тарифе 5 990 ₽.
        </p>
      </div>
      <a className="convert-limits-link" href="#answers">
        Все вопросы о пакетах
        <ArrowRight aria-hidden />
      </a>
    </div>
  );
}
