import { z } from "zod";

/**
 * Auth form schemas. Built via factories so validation messages are localized
 * (next-intl) at the call site. Field names match the API request bodies.
 */

type V = (key: string) => string;

const PASSWORD_MIN = 8;

function emailField(v: V) {
  return z
    .string()
    .min(1, v("required"))
    .email(v("email"));
}

function passwordField(v: V) {
  return z
    .string()
    .min(PASSWORD_MIN, v("passwordMin"))
    .regex(/[A-Za-z]/, v("passwordComplexity"))
    .regex(/[0-9]/, v("passwordComplexity"));
}

export function loginSchema(v: V) {
  return z.object({
    email: emailField(v),
    password: z.string().min(1, v("required")),
  });
}
export type LoginValues = z.infer<ReturnType<typeof loginSchema>>;

export function registerSchema(v: V) {
  return z
    .object({
      email: emailField(v),
      password: passwordField(v),
      confirm_password: z.string().min(1, v("required")),
      accept_terms: z.literal(true, {
        errorMap: () => ({ message: v("acceptTerms") }),
      }),
    })
    .refine((data) => data.password === data.confirm_password, {
      path: ["confirm_password"],
      message: v("passwordMismatch"),
    });
}
export type RegisterValues = z.infer<ReturnType<typeof registerSchema>>;

export function forgotPasswordSchema(v: V) {
  return z.object({ email: emailField(v) });
}
export type ForgotPasswordValues = z.infer<
  ReturnType<typeof forgotPasswordSchema>
>;

export function resetPasswordSchema(v: V) {
  return z
    .object({
      password: passwordField(v),
      confirm_password: z.string().min(1, v("required")),
    })
    .refine((data) => data.password === data.confirm_password, {
      path: ["confirm_password"],
      message: v("passwordMismatch"),
    });
}
export type ResetPasswordValues = z.infer<
  ReturnType<typeof resetPasswordSchema>
>;

export function changePasswordSchema(v: V) {
  return z
    .object({
      current_password: z.string().min(1, v("required")),
      new_password: passwordField(v),
      confirm_password: z.string().min(1, v("required")),
    })
    .refine((data) => data.new_password === data.confirm_password, {
      path: ["confirm_password"],
      message: v("passwordMismatch"),
    });
}
export type ChangePasswordValues = z.infer<
  ReturnType<typeof changePasswordSchema>
>;
