import { Link, Navigate } from "react-router-dom";
import { AuthForm } from "../components/AuthForm";
import { useLogin, useMe } from "../features/auth/useAuth";

export function LoginPage() {
  const { data: user } = useMe();
  const login = useLogin();

  if (user) {
    return <Navigate to="/" replace />;
  }

  return (
    <AuthForm
      title="Вход"
      submitLabel="Войти"
      pending={login.isPending}
      serverError={login.error?.message ?? null}
      onSubmit={(email, password) => login.mutate({ email, password })}
      onEdit={() => login.reset()}
      passwordAutoComplete="current-password"
      footer={
        <>
          Нет аккаунта?{" "}
          <Link to="/register" className="font-medium text-slate-900 underline dark:text-slate-100">
            Регистрация
          </Link>
        </>
      }
    />
  );
}
