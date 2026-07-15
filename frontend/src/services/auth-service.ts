import { apiClient } from "./api-client";

export type AuthUser = {
  id: string;
  email: string;
  username: string | null;
  phone: string | null;
  name: string | null;
  provider: "password" | "google";
};

export type AuthSession = { token: string; user: AuthUser };

const TOKEN_KEY = "commute_auth_token";
const USER_KEY = "commute_auth_user";

export async function requestSignupOtp(input: { email: string; phone: string; name?: string }) {
  const { data } = await apiClient.post<{ message: string; email_sent: boolean; dev_otp?: string }>(
    "/auth/signup/request-otp",
    input,
  );
  return data;
}

export async function verifySignupOtp(input: { email: string; code: string }) {
  const { data } = await apiClient.post<{ message: string; signup_token: string }>(
    "/auth/signup/verify-otp",
    input,
  );
  return data;
}

export async function completeSignup(input: {
  email: string;
  signup_token: string;
  password: string;
  confirm_password: string;
}) {
  const { data } = await apiClient.post<AuthSession>("/auth/signup/complete", input);
  return data;
}

// Direct username + password signup (no email OTP). Alternative to the
// requestSignupOtp → verifySignupOtp → completeSignup flow above.
export async function register(input: {
  email: string;
  username: string;
  password: string;
  confirm_password: string;
}) {
  const { data } = await apiClient.post<AuthSession>("/auth/register", input);
  return data;
}

export async function login(input: { identifier: string; password: string }) {
  const { data } = await apiClient.post<AuthSession>("/auth/login", input);
  return data;
}

export async function googleSignIn(input: { credential?: string; email?: string; name?: string }) {
  const { data } = await apiClient.post<AuthSession>("/auth/google", input);
  return data;
}

function authHeaders() {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function updateAccount(input: { name?: string; phone?: string }) {
  const { data } = await apiClient.patch<{ user: AuthUser; message: string }>("/auth/me", input, {
    headers: authHeaders(),
  });
  localStorage.setItem(USER_KEY, JSON.stringify(data.user));
  return data;
}

export async function changePassword(input: {
  current_password: string;
  new_password: string;
  confirm_password: string;
}) {
  const { data } = await apiClient.post<{ message: string }>("/auth/change-password", input, {
    headers: authHeaders(),
  });
  return data;
}

export async function logout() {
  const token = getStoredToken();
  if (token) {
    await apiClient.post("/auth/logout", undefined, { headers: { Authorization: `Bearer ${token}` } }).catch(() => undefined);
  }
  clearSession();
}

export function saveSession(session: AuthSession) {
  localStorage.setItem(TOKEN_KEY, session.token);
  localStorage.setItem(USER_KEY, JSON.stringify(session.user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}
