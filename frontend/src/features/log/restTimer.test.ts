import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_REST_SECONDS,
  IDLE_TIMER,
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
} from "./restTimer";

const T0 = 1_000_000;

describe("remainingSeconds", () => {
  it("считает от метки окончания и округляет вверх", () => {
    const endsAt = T0 + 90_000;
    expect(remainingSeconds(endsAt, T0)).toBe(90);
    expect(remainingSeconds(endsAt, T0 + 1)).toBe(90);
    expect(remainingSeconds(endsAt, T0 + 1_000)).toBe(89);
    expect(remainingSeconds(endsAt, T0 + 89_500)).toBe(1);
  });

  it("не уходит ниже нуля и не зависит от числа тиков", () => {
    const endsAt = T0 + 5_000;
    expect(remainingSeconds(endsAt, T0 + 5_000)).toBe(0);
    expect(remainingSeconds(endsAt, T0 + 60_000)).toBe(0);
  });

  it("не растягивается, если вкладка спала: остаток берётся по текущему времени", () => {
    const state = startTimer(90, T0);
    // Вкладка в фоне 40 секунд: тики не приходили, но метка времени та же.
    expect(displaySeconds(state, 90, T0 + 40_000)).toBe(50);
  });
});

describe("startTimer, pauseTimer, resumeTimer", () => {
  it("пауза фиксирует остаток, продолжение отсчитывает от нового момента", () => {
    const running = startTimer(90, T0);
    const paused = pauseTimer(running, T0 + 30_000);
    expect(paused).toEqual({ status: "paused", remaining: 60, endsAt: null });

    const resumed = resumeTimer(paused, T0 + 100_000);
    expect(resumed).toEqual({ status: "running", remaining: 60, endsAt: T0 + 160_000 });
    expect(displaySeconds(resumed, 90, T0 + 100_000)).toBe(60);
  });

  it("пауза и продолжение не меняют состояние в неподходящей фазе", () => {
    expect(pauseTimer(IDLE_TIMER, T0)).toBe(IDLE_TIMER);
    expect(resumeTimer(startTimer(30, T0), T0)).toEqual(startTimer(30, T0));
  });

  it("повторный старт сбрасывает отсчёт на новую длительность", () => {
    const again = startTimer(120, T0 + 50_000);
    expect(displaySeconds(again, 90, T0 + 50_000)).toBe(120);
  });
});

describe("adjustRunningTimer", () => {
  it("плюс и минус 15 секунд сдвигают метку окончания", () => {
    const running = startTimer(90, T0);
    const plus = adjustRunningTimer(running, 15, T0);
    expect(displaySeconds(plus, 90, T0)).toBe(105);
    const minus = adjustRunningTimer(plus, -15, T0);
    expect(displaySeconds(minus, 90, T0)).toBe(90);
  });

  it("минус до нуля заканчивает отсчёт", () => {
    const running = startTimer(10, T0);
    expect(adjustRunningTimer(running, -15, T0)).toEqual(finishTimer());
  });

  it("на паузе меняет остаток и не даёт уйти ниже нуля", () => {
    const paused = pauseTimer(startTimer(90, T0), T0);
    expect(adjustRunningTimer(paused, 15, T0)).toEqual({ status: "paused", remaining: 105, endsAt: null });
    expect(adjustRunningTimer(paused, -90, T0)).toEqual(finishTimer());
  });
});

describe("displaySeconds", () => {
  it("в простое показывает длительность по умолчанию, после окончания — ноль", () => {
    expect(displaySeconds(IDLE_TIMER, 90, T0)).toBe(90);
    expect(displaySeconds(finishTimer(), 90, T0)).toBe(0);
  });
});

describe("formatClock", () => {
  it("печатает минуты и секунды с ведущими нулями", () => {
    expect(formatClock(0)).toBe("00:00");
    expect(formatClock(9)).toBe("00:09");
    expect(formatClock(90)).toBe("01:30");
    expect(formatClock(600)).toBe("10:00");
  });
});

describe("clampRestSeconds", () => {
  it("держит значение в пределах от 15 до 1800 секунд", () => {
    expect(clampRestSeconds(5)).toBe(15);
    expect(clampRestSeconds(90.4)).toBe(90);
    expect(clampRestSeconds(5000)).toBe(1800);
    expect(clampRestSeconds(Number.NaN)).toBe(DEFAULT_REST_SECONDS);
  });
});

describe("хранение длительности", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("без записи возвращает 90 секунд", () => {
    expect(readStoredRest()).toBe(90);
  });

  it("помнит значение, заданное пользователем", () => {
    writeStoredRest(120);
    expect(localStorage.getItem("fc-rest-timer-seconds")).toBe("120");
    expect(readStoredRest()).toBe(120);
  });

  it("битое значение в localStorage не ломает экран", () => {
    localStorage.setItem("fc-rest-timer-seconds", "много");
    expect(readStoredRest()).toBe(90);
  });

  it("недоступное хранилище не считается ошибкой", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(readStoredRest()).toBe(90);
    expect(() => writeStoredRest(60)).not.toThrow();
  });
});
