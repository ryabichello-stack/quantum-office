const counterId = Number(process.env.NEXT_PUBLIC_YM_COUNTER_ID || 0);

type YandexMetrikaWindow = Window & {
  ym?: (id: number, method: "reachGoal", goal: string) => void;
};

export function reachGoal(goal: string) {
  if (!counterId || typeof window === "undefined") return;
  (window as YandexMetrikaWindow).ym?.(counterId, "reachGoal", goal);
}
