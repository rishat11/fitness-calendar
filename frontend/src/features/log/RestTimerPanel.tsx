import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { playAlarm, releaseSound, stopAlarm, unlockSound } from "./alarm";
import {
  IDLE_TIMER,
  REST_STEP_SECONDS,
  adjustRunningTimer,
  clampRestSeconds,
  displaySeconds,
  finishTimer,
  formatClock,
  pauseTimer,
  readStoredRest,
  remainingSeconds,
  resumeTimer,
  startTimer,
  writeStoredRest,
  type TimerState,
} from "./restTimer";

const TICK_MS = 250;

const buttonClass =
  "min-h-11 rounded-lg border border-slate-300 px-3 text-sm font-medium text-slate-700 hover:bg-slate-200 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800";
const primaryClass =
  "min-h-11 rounded-lg bg-slate-900 px-3 text-sm font-medium text-white hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300";

const STATUS_LABEL: Record<TimerState["status"], string> = {
  idle: "Отдых не идёт",
  running: "Отдых",
  paused: "На паузе",
  done: "Отдых окончен",
};

export type RestTimerHandle = {
  /** Запускает отсчёт на отдых подхода. Нет отдыха (null или 0) — таймер не стартует. */
  autoStart: (seconds: number | null) => void;
  reset: () => void;
};

/** Таймер отдыха на экране тренировки. Тики живут здесь, чтобы не перерисовывать весь лог. */
export function RestTimerPanel({ ref }: { ref: Ref<RestTimerHandle> }) {
  const [configured, setConfigured] = useState<number>(readStoredRest);
  const [state, setState] = useState<TimerState>(IDLE_TIMER);
  const [now, setNow] = useState(() => Date.now());
  const [soundHint, setSoundHint] = useState(false);
  const stateRef = useRef<TimerState>(IDLE_TIMER);
  const configuredRef = useRef(configured);

  const transition = (next: TimerState) => {
    const prev = stateRef.current;
    stateRef.current = next;
    // Метку «сейчас» обновляем вместе с состоянием, иначе первый кадр покажет устаревшее время.
    setNow(Date.now());
    setState(next);
    if (prev.status === "running" && next.status === "done") {
      void playAlarm().then((result) => {
        if (result === "blocked") setSoundHint(true);
      });
    }
  };

  const running = state.status === "running";
  useEffect(() => {
    if (!running) return;
    const check = () => {
      const at = Date.now();
      setNow(at);
      const current = stateRef.current;
      if (current.status === "running" && current.endsAt != null && remainingSeconds(current.endsAt, at) === 0) {
        transition(finishTimer());
      }
    };
    check();
    const id = window.setInterval(check, TICK_MS);
    document.addEventListener("visibilitychange", check);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", check);
    };
  }, [running]);

  useEffect(() => () => releaseSound(), []);

  useImperativeHandle(ref, () => ({
    autoStart: (seconds) => {
      if (seconds == null || seconds <= 0) return;
      stopAlarm();
      transition(startTimer(seconds, Date.now()));
    },
    reset: () => {
      stopAlarm();
      transition(IDLE_TIMER);
    },
  }));

  const onToggle = () => {
    unlockSound();
    stopAlarm();
    const current = stateRef.current;
    const at = Date.now();
    if (current.status === "running") transition(pauseTimer(current, at));
    else if (current.status === "paused") transition(resumeTimer(current, at));
    else transition(startTimer(configuredRef.current, at));
  };

  const onReset = () => {
    stopAlarm();
    transition(IDLE_TIMER);
  };

  const onAdjust = (delta: number) => {
    const current = stateRef.current;
    if (current.status === "running" || current.status === "paused") {
      transition(adjustRunningTimer(current, delta, Date.now()));
      return;
    }
    // В простое меняем длительность по умолчанию и помним её на этом устройстве.
    const next = clampRestSeconds(configuredRef.current + delta);
    configuredRef.current = next;
    setConfigured(next);
    writeStoredRest(next);
    if (current.status === "done") {
      stopAlarm();
      transition(IDLE_TIMER);
    }
  };

  const onEnableSound = () => {
    unlockSound();
    setSoundHint(false);
  };

  const shown = displaySeconds(state, configured, now);

  return (
    <section
      aria-label="Таймер отдыха"
      className="sticky top-0 z-10 flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-950"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-slate-600 dark:text-slate-300">{STATUS_LABEL[state.status]}</p>
        <button type="button" className={buttonClass} onClick={onEnableSound}>
          Включить звук
        </button>
      </div>
      <p role="timer" aria-label="Осталось отдыхать" className="text-center text-6xl font-semibold tabular-nums">
        {formatClock(shown)}
      </p>
      {soundHint && (
        <p aria-live="polite" className="text-sm text-amber-700 dark:text-amber-300">
          Звук заблокирован браузером. Нажмите «Включить звук», чтобы слышать сигнал таймера.
        </p>
      )}
      <div className="grid grid-cols-4 gap-2">
        <button
          type="button"
          className={buttonClass}
          aria-label="Минус 15 секунд"
          onClick={() => onAdjust(-REST_STEP_SECONDS)}
        >
          −15
        </button>
        <button type="button" className={primaryClass} onClick={onToggle}>
          {running ? "Пауза" : "Старт"}
        </button>
        <button type="button" className={buttonClass} aria-label="Плюс 15 секунд" onClick={() => onAdjust(REST_STEP_SECONDS)}>
          +15
        </button>
        <button type="button" className={buttonClass} onClick={onReset}>
          Сброс
        </button>
      </div>
    </section>
  );
}
