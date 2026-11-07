/**
 * Сигнал таймера отдыха: короткие гудки через Web Audio API и вибрация.
 * Отсутствие API — не сбой: функции просто возвращают "unsupported".
 */

export type AlarmResult = "played" | "blocked" | "unsupported";

let context: AudioContext | null = null;
let oscillators: OscillatorNode[] = [];

function getContext(): AudioContext | null {
  if (context) return context;
  if (typeof window === "undefined") return null;
  const Ctor: typeof AudioContext | undefined =
    window.AudioContext ?? (window as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  try {
    context = new Ctor();
  } catch {
    context = null;
  }
  return context;
}

/** Вызывать из жеста пользователя (нажатие кнопки): так браузер разрешает звук. */
export function unlockSound(): void {
  const ctx = getContext();
  if (ctx && ctx.state === "suspended") void ctx.resume().catch(() => {});
}

function vibrate(pattern: number | number[]): void {
  try {
    if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
      navigator.vibrate(pattern);
    }
  } catch {
    // Браузер может отказать в вибрации вне жеста; сигнал остаётся звуковым.
  }
}

/** Три коротких гудка и вибрация. Если звук заблокирован, возвращает "blocked". */
export async function playAlarm(): Promise<AlarmResult> {
  vibrate([300, 150, 300]);
  const ctx = getContext();
  if (!ctx) return "unsupported";
  if (ctx.state === "suspended") {
    try {
      await ctx.resume();
    } catch {
      return "blocked";
    }
  }
  if (ctx.state !== "running") return "blocked";

  const start = ctx.currentTime + 0.02;
  for (let pulse = 0; pulse < 3; pulse += 1) {
    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();
    const at = start + pulse * 0.25;
    oscillator.type = "sine";
    oscillator.frequency.value = 880;
    gain.gain.setValueAtTime(0.25, at);
    gain.gain.setValueAtTime(0, at + 0.15);
    oscillator.connect(gain);
    gain.connect(ctx.destination);
    oscillator.start(at);
    oscillator.stop(at + 0.15);
    oscillators.push(oscillator);
  }
  return "played";
}

/** Останавливает гудки и вибрацию: при сбросе, завершении тренировки и уходе со страницы. */
export function stopAlarm(): void {
  for (const oscillator of oscillators) {
    try {
      oscillator.stop();
    } catch {
      // Уже остановлен.
    }
  }
  oscillators = [];
  vibrate(0);
}

/** Закрывает аудиоконтекст при уходе со страницы. Новый создастся при следующем жесте. */
export function releaseSound(): void {
  stopAlarm();
  if (context) {
    void context.close().catch(() => {});
    context = null;
  }
}
