import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useLogout, useMe } from "../features/auth/useAuth";
import {
  nextThemePreference,
  useTheme,
  type ThemePreference,
} from "../features/theme/useTheme";
import {
  PROFILE_QUERY_KEY,
  toProfileUpdate,
  useProfile,
  useUpdateProfile,
} from "../features/profile/useProfile";
import { NAV_ITEMS } from "../navigation";

const linkBase =
  "flex min-h-11 items-center gap-2 rounded-xl px-3 text-sm font-medium transition-all duration-150";
const linkActive =
  "bg-white text-stone-900 shadow-sm shadow-stone-900/5 ring-1 ring-stone-200 dark:bg-white/10 dark:text-white dark:ring-white/10";
const linkIdle =
  "text-stone-600 hover:bg-white/70 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-white/5 dark:hover:text-stone-100";
const iconButton =
  "flex size-11 items-center justify-center rounded-xl text-lg transition hover:bg-white/80 dark:hover:bg-white/10";

const THEME_ICON: Record<ThemePreference, string> = {
  system: "◐",
  light: "☀️",
  dark: "🌙",
};

const THEME_LABEL: Record<ThemePreference, string> = {
  system: "как в системе",
  light: "светлая",
  dark: "тёмная",
};

function ThemeToggle() {
  const { preference, setTheme } = useTheme();
  const queryClient = useQueryClient();
  const updateProfile = useUpdateProfile();
  const next = nextThemePreference(preference);

  const handleToggle = async () => {
    setTheme(next);
    // PUT заменяет весь профиль, поэтому берём свежую копию с сервера: кэш мог устареть и откатить чужие поля.
    try {
      const fresh = await queryClient.fetchQuery({
        queryKey: PROFILE_QUERY_KEY,
        queryFn: () => api.getProfile(),
        staleTime: 0,
      });
      updateProfile.mutate(toProfileUpdate(fresh, { theme: next }));
    } catch {
      // Сеть недоступна: тема уже применена локально, сохранение на сервер пропускаем.
    }
  };

  return (
    <button
      type="button"
      onClick={handleToggle}
      aria-label={`Тема: ${THEME_LABEL[preference]}. Переключить на: ${THEME_LABEL[next]}`}
      title={`Тема: ${THEME_LABEL[preference]}`}
      className={iconButton}
    >
      {THEME_ICON[preference]}
    </button>
  );
}

/** Сервер — источник истины для темы: при загрузке или смене профиля применяем его значение. */
function useSyncThemeWithProfile() {
  const { data: profile } = useProfile();
  const { setTheme } = useTheme();
  const serverTheme = profile?.theme;

  useEffect(() => {
    if (serverTheme) {
      setTheme(serverTheme);
    }
  }, [serverTheme, setTheme]);
}

export function AppLayout() {
  const { data: user } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  useSyncThemeWithProfile();

  const handleLogout = () => {
    logout.mutate(undefined, {
      onSettled: () => navigate("/login", { replace: true }),
    });
  };

  return (
    <div className="min-h-dvh md:flex">
      {/* Боковая навигация: только от md (768 px) */}
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col gap-2 border-r border-stone-200/80 bg-stone-100/60 p-4 backdrop-blur md:flex dark:border-white/10 dark:bg-white/[0.02]">
        <div className="mb-6 flex items-center gap-2.5 px-2">
          <span className="flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-400 to-emerald-600 text-base text-white shadow-md shadow-emerald-600/30">
            ⚡
          </span>
          <span className="text-base font-bold tracking-tight">Фитнес-календарь</span>
        </div>
        <nav className="flex flex-col gap-1" aria-label="Основная навигация">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => `${linkBase} ${isActive ? linkActive : linkIdle}`}
            >
              {item.label}
            </NavLink>
          ))}
          <NavLink
            to="/settings"
            className={({ isActive }) => `${linkBase} ${isActive ? linkActive : linkIdle}`}
          >
            Настройки
          </NavLink>
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-stone-200/80 bg-white/70 px-4 py-2.5 backdrop-blur-md dark:border-white/10 dark:bg-[#0b0f14]/70">
          <span className="truncate text-base font-bold tracking-tight md:hidden">Фитнес-календарь</span>
          <span className="hidden truncate rounded-full bg-stone-100 px-3 py-1 text-sm text-stone-600 md:block dark:bg-white/5 dark:text-stone-300">{user?.email}</span>
          <div className="flex items-center gap-1">
            <ThemeToggle />
            <NavLink to="/settings" aria-label="Настройки" className={iconButton}>
              ⚙️
            </NavLink>
            <button
              type="button"
              onClick={handleLogout}
              disabled={logout.isPending}
              className="flex min-h-11 items-center rounded-xl px-3 text-sm font-medium text-stone-600 transition hover:bg-white/80 disabled:opacity-50 dark:text-stone-300 dark:hover:bg-white/10"
            >
              Выйти
            </button>
          </div>
        </header>

        <main className="w-full flex-1 p-4 pb-24 md:pb-4">
          <Outlet />
        </main>
      </div>

      {/* Нижняя панель навигации: только до md */}
      <nav
        aria-label="Основная навигация"
        className="fixed inset-x-0 bottom-0 z-10 grid border-t border-stone-200/80 bg-white/85 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden dark:border-white/10 dark:bg-[#0b0f14]/85"
        style={{ gridTemplateColumns: `repeat(${NAV_ITEMS.length}, minmax(0, 1fr))` }}
      >
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex min-h-11 flex-col items-center justify-center px-1 py-2 text-[11px] font-medium transition ${
                isActive ? "text-emerald-700 dark:text-emerald-400" : "text-stone-500 dark:text-stone-400"
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
