import { useState, type FormEvent, type ReactNode } from "react";
import { validateCredentials, type CredentialsErrors } from "../features/auth/validation";

type AuthFormProps = {
  title: string;
  submitLabel: string;
  pending: boolean;
  serverError: string | null;
  onSubmit: (email: string, password: string) => void;
  /** Вызывается при изменении полей: страница сбрасывает серверную ошибку. */
  onEdit: () => void;
  footer: ReactNode;
  passwordAutoComplete: "current-password" | "new-password";
};

const inputClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/20 dark:border-slate-700 dark:bg-slate-900 dark:focus:border-slate-300 dark:focus:ring-slate-300/20";

export function AuthForm({
  title,
  submitLabel,
  pending,
  serverError,
  onSubmit,
  onEdit,
  footer,
  passwordAutoComplete,
}: AuthFormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<CredentialsErrors>({});

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextErrors = validateCredentials(email, password);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length === 0) {
      onSubmit(email.trim(), password);
    }
  };

  return (
    <div className="mx-auto w-full max-w-sm py-8">
      <h1 className="mb-6 text-2xl font-semibold">{title}</h1>

      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="auth-email" className="text-sm font-medium">
            Email
          </label>
          <input
            id="auth-email"
            name="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              onEdit();
            }}
            className={inputClass}
            aria-invalid={errors.email ? true : undefined}
            aria-describedby={errors.email ? "auth-email-error" : undefined}
          />
          {errors.email && (
            <span id="auth-email-error" className="text-sm text-red-600">
              {errors.email}
            </span>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="auth-password" className="text-sm font-medium">
            Пароль
          </label>
          <input
            id="auth-password"
            name="password"
            type="password"
            autoComplete={passwordAutoComplete}
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              onEdit();
            }}
            className={inputClass}
            aria-invalid={errors.password ? true : undefined}
            aria-describedby={errors.password ? "auth-password-error" : undefined}
          />
          {errors.password && (
            <span id="auth-password-error" className="text-sm text-red-600">
              {errors.password}
            </span>
          )}
        </div>

        {serverError && (
          <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            {serverError}
          </p>
        )}

        <button
          type="submit"
          disabled={pending}
          className="min-h-11 rounded-lg bg-slate-900 px-4 font-medium text-white hover:bg-slate-700 disabled:opacity-60 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
        >
          {pending ? "Подождите…" : submitLabel}
        </button>
      </form>

      <div className="mt-6 text-center text-sm text-slate-600 dark:text-slate-300">{footer}</div>
    </div>
  );
}
