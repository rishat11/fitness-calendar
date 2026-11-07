/** Таймер отдыха: чистая логика. Отсчёт идёт от метки времени окончания, а не от числа тиков. */

export const DEFAULT_REST_SECONDS = 90;
export const REST_STEP_SECONDS = 15;
export const REST_MIN_SECONDS = 15;
export const REST_MAX_SECONDS = 1800;
const STORAGE_KEY = "fc-rest-timer-seconds";

export type TimerStatus = "idle" | "running" | "paused" | "done";

export type TimerState = {
  status: TimerStatus;
  /** Оставшиеся секунды на паузе; 0 после окончания. */
  remaining: number;
  /** Метка времени окончания (мс), только пока таймер идёт. */
  endsAt: number | null;
};

export const IDLE_TIMER: TimerState = { status: "idle", remaining: 0, endsAt: null };

/** Сколько секунд осталось до метки времени. Округление вверх: 90 показываем сразу после старта. */
export function remainingSeconds(endsAt: number, now: number): number {
  return Math.max(0, Math.ceil((endsAt - now) / 1000));
}

export function clampRestSeconds(seconds: number): number {
  if (!Number.isFinite(seconds)) return DEFAULT_REST_SECONDS;
  return Math.min(REST_MAX_SECONDS, Math.max(REST_MIN_SECONDS, Math.round(seconds)));
}

export function startTimer(seconds: number, now: number): TimerState {
  return { status: "running", remaining: seconds, endsAt: now + seconds * 1000 };
}

export function pauseTimer(state: TimerState, now: number): TimerState {
  if (state.status !== "running" || state.endsAt == null) return state;
  return { status: "paused", remaining: remainingSeconds(state.endsAt, now), endsAt: null };
}

export function resumeTimer(state: TimerState, now: number): TimerState {
  if (state.status !== "paused") return state;
  return startTimer(state.remaining, now);
}

export function finishTimer(): TimerState {
  return { status: "done", remaining: 0, endsAt: null };
}

/** Сдвиг на ±15 секунд во время отсчёта или паузы. Дошли до нуля — таймер закончился. */
export function adjustRunningTimer(state: TimerState, deltaSeconds: number, now: number): TimerState {
  if (state.status === "running" && state.endsAt != null) {
    const endsAt = state.endsAt + deltaSeconds * 1000;
    if (remainingSeconds(endsAt, now) === 0) return finishTimer();
    return { status: "running", remaining: remainingSeconds(endsAt, now), endsAt };
  }
  if (state.status === "paused") {
    const remaining = state.remaining + deltaSeconds;
    if (remaining <= 0) return finishTimer();
    return { ...state, remaining };
  }
  return state;
}

/** Что показывать на табло. В простое — длительность по умолчанию, она задаётся на экране. */
export function displaySeconds(state: TimerState, configured: number, now: number): number {
  if (state.status === "running" && state.endsAt != null) return remainingSeconds(state.endsAt, now);
  if (state.status === "paused" || state.status === "done") return state.remaining;
  return configured;
}

export function formatClock(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function storage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

/** Длительность, которую пользователь задал вручную. Нет или битое значение — 90 секунд. */
export function readStoredRest(): number {
  try {
    const raw = storage()?.getItem(STORAGE_KEY);
    if (raw == null) return DEFAULT_REST_SECONDS;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? clampRestSeconds(parsed) : DEFAULT_REST_SECONDS;
  } catch {
    return DEFAULT_REST_SECONDS;
  }
}

export function writeStoredRest(seconds: number): void {
  try {
    storage()?.setItem(STORAGE_KEY, String(clampRestSeconds(seconds)));
  } catch {
    // Приватный режим или переполненное хранилище: таймер работает и без памяти.
  }
}
