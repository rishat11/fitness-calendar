import { useCallback, useSyncExternalStore } from "react";

/** Выбор пользователя: «system» означает следовать настройке ОС. */
export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";
const listeners = new Set<() => void>();

function readPreference(): ThemePreference {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark" || stored === "system") {
    return stored;
  }
  return "system";
}

function resolve(preference: ThemePreference): ResolvedTheme {
  if (preference !== "system") {
    return preference;
  }
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

function applyTheme(preference: ThemePreference) {
  const resolved = resolve(preference);
  document.documentElement.classList.toggle("dark", resolved === "dark");
  document.documentElement.style.colorScheme = resolved;
}

/** Применяет сохранённую тему до первого рендера, чтобы не было вспышки. */
export function initTheme() {
  applyTheme(readPreference());
  // Если выбрано «как в системе», следуем за сменой темы ОС без перезагрузки.
  window.matchMedia(DARK_QUERY).addEventListener("change", () => {
    if (readPreference() === "system") {
      applyTheme("system");
    }
  });
}

const THEME_CYCLE: ThemePreference[] = ["system", "light", "dark"];

/** Следующая настройка при нажатии на переключатель: «как в системе» → светлая → тёмная → «как в системе». */
export function nextThemePreference(current: ThemePreference): ThemePreference {
  return THEME_CYCLE[(THEME_CYCLE.indexOf(current) + 1) % THEME_CYCLE.length];
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Локальная копия темы. Сервер (профиль) становится источником истины после входа;
 * здесь значение хранится, чтобы тема применялась сразу, без ожидания сети.
 */
export function useTheme() {
  const preference = useSyncExternalStore(subscribe, readPreference, () => "system" as const);

  const setTheme = useCallback((next: ThemePreference) => {
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
    listeners.forEach((listener) => listener());
  }, []);

  return { preference, resolvedTheme: resolve(preference), setTheme };
}
