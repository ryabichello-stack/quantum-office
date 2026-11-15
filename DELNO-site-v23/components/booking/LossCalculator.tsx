"use client";

import { useState } from "react";

const number = (value: string) => Math.max(0, Number(value) || 0);
const rub = (value: number) => new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(Math.round(value));

export function LossCalculator() {
  const [requests, setRequests] = useState("100");
  const [missed, setMissed] = useState("15");
  const [qualified, setQualified] = useState("60");
  const [conversion, setConversion] = useState("30");
  const [margin, setMargin] = useState("2500");

  const missedRequests = number(requests) * Math.min(100, number(missed)) / 100;
  const potentialOrders = missedRequests * Math.min(100, number(qualified)) / 100 * Math.min(100, number(conversion)) / 100;
  const potentialMargin = potentialOrders * number(margin);

  return (
    <section className="dc-tool" aria-labelledby="loss-calculator-title">
      <div className="dc-tool-intro">
        <p className="dv17-eyebrow">Посчитайте на своих данных</p>
        <h2 id="loss-calculator-title">Сколько могут стоить пропущенные обращения</h2>
        <p>Это оценка возможной недополученной маржи, а не прогноз результата DELNO. Все значения можно изменить.</p>
      </div>
      <div className="dc-tool-grid">
        <label>Обращений в месяц<input type="number" min="0" inputMode="numeric" value={requests} onChange={e => setRequests(e.target.value)} /></label>
        <label>Не получили ответ, %<input type="number" min="0" max="100" inputMode="decimal" value={missed} onChange={e => setMissed(e.target.value)} /></label>
        <label>Из них целевые, %<input type="number" min="0" max="100" inputMode="decimal" value={qualified} onChange={e => setQualified(e.target.value)} /></label>
        <label>Могли стать заказами, %<input type="number" min="0" max="100" inputMode="decimal" value={conversion} onChange={e => setConversion(e.target.value)} /></label>
        <label>Маржа с одного заказа, ₽<input type="number" min="0" inputMode="decimal" value={margin} onChange={e => setMargin(e.target.value)} /></label>
      </div>
      <div className="dc-tool-result" aria-live="polite">
        <span>Возможная потеря за месяц</span>
        <strong>{rub(potentialMargin)} ₽</strong>
        <small>Примерно {rub(missedRequests)} обращений без ответа × доля целевых × конверсия × маржа заказа. Часть людей могла обратиться повторно или купить иначе.</small>
      </div>
    </section>
  );
}
