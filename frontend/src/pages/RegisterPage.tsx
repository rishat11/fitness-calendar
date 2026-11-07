import { Link, Navigate } from "react-router-dom";
import { AuthForm } from "../components/AuthForm";
import { useMe, useRegister } from "../features/auth/useAuth";

export function RegisterPage() {
  const { data: user } = useMe();
  const register = useRegister();

  if (user) {
    return <Navigate to="/" replace />;
  }

  return (
    <AuthForm
      title="Регистрация"
      submitLabel="Создать аккаунт"
      pending={register.isPending}
      serverError={register.error?.message ?? null}
      onSubmit={(email, password) => register.mutate({ email, password })}
      onEdit={() => register.reset()}
      passwordAutoComplete="new-password"
      footer={
        <>
          Уже есть аккаунт?{" "}
          <Link to="/login" className="font-medium text-slate-900 underline dark:text-slate-100">
            Войти
          </Link>
        </>
      }
    />
  );
}
