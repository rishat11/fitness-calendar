import { Navigate, Outlet } from "react-router-dom";
import { useMe } from "../features/auth/useAuth";

export function ProtectedRoute() {
  const { data: user, isPending, isError } = useMe();

  if (isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center text-slate-600 dark:text-slate-300">Загрузка…</div>
    );
  }

  if (isError) {
    return (
      <div className="flex min-h-dvh items-center justify-center p-4 text-center text-red-600">
        Не удалось проверить вход. Обновите страницу.
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
