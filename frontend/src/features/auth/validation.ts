const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 128;

export type CredentialsErrors = {
  email?: string;
  password?: string;
};

export function validateCredentials(email: string, password: string): CredentialsErrors {
  const errors: CredentialsErrors = {};
  if (!EMAIL_PATTERN.test(email.trim())) {
    errors.email = "Введите корректный email";
  }
  if (password.length < PASSWORD_MIN_LENGTH) {
    errors.password = `Пароль должен быть не короче ${PASSWORD_MIN_LENGTH} символов`;
  } else if (password.length > PASSWORD_MAX_LENGTH) {
    errors.password = `Пароль должен быть не длиннее ${PASSWORD_MAX_LENGTH} символов`;
  }
  return errors;
}
