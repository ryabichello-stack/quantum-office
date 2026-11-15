"use client";

import { useState } from "react";

const safe = (value: string) => Math.max(0, Number(value) || 0);
const rub = (value: number) => new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(Math.round(value));

export function NoShowCalculator() {
  const [emptySlots, setEmptySlots] = useState("10");
  const [price, setPrice] = useState("3000");
  const [variableCost, setVariableCost] = useState("500");
  const [replacementDemand, setReplacementDemand] = useState("50");

  const margin = Math.max(0, safe(price) - safe(variableCost));
  const demandShare = Math.min(100, safe(replacementDemand)) / 100;
  const possibleLoss = safe(emptySlots) * margin * demandShare;

  return <section className="dc-tool" aria-labelledby="no-show-calculator-title">
    <div className="dc-tool-intro">
      <p className="dv17-eyebrow">Инструмент для своего расписания</p>
      <h2 id="no-show-calculator-title">Сколько могут стоить пустые окна</h2>
      <p>Оценка показывает возможную недополученную маржу там, где на освободившееся время был спрос. Это не обещание вернуть сумму автоматически.</p>
    </div>
    <div className="dc-tool-grid">
      <label>Незаполненных окон за месяц<input type="number" min="0" inputMode="numeric" value={emptySlots} onChange={event => setEmptySlots(event.target.value)} /></label>
      <label>Цена одного визита, ₽<input type="number" min="0" inputMode="decimal" value={price} onChange={event => setPrice(event.target.value)} /></label>
      <label>Переменные расходы на визит, ₽<input type="number" min="0" inputMode="decimal" value={variableCost} onChange={event => setVariableCost(event.target.value)} /></label>
      <label>Окон, на которые был спрос, %<input type="number" min="0" max="100" inputMode="decimal" value={replacementDemand} onChange={event => setReplacementDemand(event.target.value)} /></label>
    </div>
    <div className="dc-tool-result" aria-live="polite">
      <span>Возможная недополученная маржа за месяц</span>
      <strong>{rub(possibleLoss)} ₽</strong>
      <small>{rub(safe(emptySlots))} пустых окон × ({rub(safe(price))} ₽ − {rub(safe(variableCost))} ₽) × {rub(demandShare * 100)}% вероятного спроса. Используйте собственные данные; неявка не всегда означает потерянную продажу.</small>
    </div>
  </section>;
}
