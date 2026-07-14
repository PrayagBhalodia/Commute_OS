"use client";

import Link from "next/link";
import Script from "next/script";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, CalendarClock, CheckCircle2, KeyRound, Loader2, MailCheck, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  completeSignup,
  googleSignIn,
  login,
  requestSignupOtp,
  saveSession,
  verifySignupOtp,
} from "@/services/auth-service";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

type Mode = "login" | "signup";
type SignupStep = "details" | "otp" | "password";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: { client_id: string; callback: (response: { credential: string }) => void }) => void;
          renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
        };
      };
    };
  }
}

function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Something went wrong. Please try again.";
}

// Where to go after a successful sign-in (set by the auth guard as ?next=/plan).
function nextPath(): string {
  if (typeof window === "undefined") return "/";
  const next = new URLSearchParams(window.location.search).get("next");
  return next && next.startsWith("/") && !next.startsWith("/auth") ? next : "/";
}

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [step, setStep] = useState<SignupStep>("details");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // shared signup state
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [signupToken, setSignupToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [devOtp, setDevOtp] = useState<string | null>(null);
  const [resendIn, setResendIn] = useState(0);

  // login state
  const [identifier, setIdentifier] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  const googleButtonRef = useRef<HTMLDivElement>(null);
  const [gisReady, setGisReady] = useState(false);

  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = setInterval(() => setResendIn((s) => s - 1), 1000);
    return () => clearInterval(timer);
  }, [resendIn]);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || !gisReady || !window.google || !googleButtonRef.current) return;
    window.google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      callback: async ({ credential }) => {
        try {
          setLoading(true);
          const session = await googleSignIn({ credential });
          saveSession(session);
          router.replace(nextPath());
        } catch (err) {
          setError(errorMessage(err));
        } finally {
          setLoading(false);
        }
      },
    });
    window.google.accounts.id.renderButton(googleButtonRef.current, {
      theme: "outline",
      size: "large",
      width: 352,
      text: "continue_with",
      shape: "rectangular",
    });
  }, [gisReady, router]);

  function switchMode(next: Mode) {
    setMode(next);
    setStep("details");
    setError(null);
    setNotice(null);
  }

  async function run(action: () => Promise<void>) {
    setError(null);
    setLoading(true);
    try {
      await action();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const sendOtp = () =>
    run(async () => {
      const result = await requestSignupOtp({ email, phone, name: name || undefined });
      setDevOtp(result.dev_otp ?? null);
      setNotice(
        result.email_sent
          ? `We emailed a 6-digit code to ${email}.`
          : "Email delivery isn't configured on this server — use the development code shown below.",
      );
      setResendIn(30);
      setStep("otp");
    });

  const verifyOtp = () =>
    run(async () => {
      const result = await verifySignupOtp({ email, code: otp });
      setSignupToken(result.signup_token);
      setNotice("Email verified. Now create your password.");
      setStep("password");
    });

  const finishSignup = () =>
    run(async () => {
      if (password.length < 8) throw new Error("Password must be at least 8 characters.");
      if (password !== confirmPassword) throw new Error("Passwords do not match.");
      const session = await completeSignup({
        email,
        signup_token: signupToken ?? "",
        password,
        confirm_password: confirmPassword,
      });
      saveSession(session);
      router.replace(nextPath());
    });

  const doLogin = () =>
    run(async () => {
      const session = await login({ identifier, password: loginPassword });
      saveSession(session);
      router.replace(nextPath());
    });

  const demoGoogle = () =>
    run(async () => {
      const session = await googleSignIn({ email: "demo.google.user@gmail.com", name: "Google Demo User" });
      saveSession(session);
      router.replace(nextPath());
    });

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      {GOOGLE_CLIENT_ID ? (
        <Script src="https://accounts.google.com/gsi/client" onLoad={() => setGisReady(true)} />
      ) : null}
      <div className="w-full max-w-md space-y-6">
        <Link href="/" className="flex items-center justify-center gap-3" aria-label="Commute OS home">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-slate-950 text-white">
            <CalendarClock className="h-5 w-5" />
          </div>
          <div>
            <p className="font-semibold text-slate-950">Commute OS</p>
            <p className="text-xs text-slate-500">Journey Operating System</p>
          </div>
        </Link>

        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-soft sm:p-8">
          <div className="space-y-1 text-center">
            <p className="text-sm font-medium text-teal-700">
              {mode === "login" ? "Welcome back" : "Join Commute OS"}
            </p>
            <h1 className="text-2xl font-semibold tracking-normal text-slate-950">
              {mode === "login"
                ? "Sign in to your account"
                : step === "details"
                  ? "Create your account"
                  : step === "otp"
                    ? "Verify your email"
                    : "Set your password"}
            </h1>
            <p className="text-sm text-slate-600">
              {mode === "login"
                ? "Use your email or mobile number and password."
                : step === "details"
                  ? "We'll send a one-time code to your email to verify it's you."
                  : step === "otp"
                    ? `Enter the 6-digit code sent to ${email}.`
                    : "Choose a password of at least 8 characters."}
            </p>
          </div>

          {mode === "login" || step === "details" ? (
            <>
              <div className="mt-6 space-y-3">
                {GOOGLE_CLIENT_ID ? (
                  <div ref={googleButtonRef} className="flex justify-center" />
                ) : (
                  <Button variant="secondary" className="w-full" onClick={demoGoogle} disabled={loading}>
                    <GoogleIcon />
                    Continue with Google
                  </Button>
                )}
              </div>
              <div className="my-5 flex items-center gap-3">
                <div className="h-px flex-1 bg-slate-200" />
                <span className="text-xs uppercase tracking-wide text-slate-400">or continue with email</span>
                <div className="h-px flex-1 bg-slate-200" />
              </div>
            </>
          ) : null}

          {error ? (
            <p className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </p>
          ) : null}
          {notice && !error ? (
            <p className="mb-4 flex items-start gap-2 rounded-md border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-800">
              <MailCheck className="mt-0.5 h-4 w-4 shrink-0" /> {notice}
            </p>
          ) : null}

          {mode === "login" ? (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                doLogin();
              }}
            >
              <Field label="Email or mobile number">
                <Input
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder="you@example.com or 98765 43210"
                  autoComplete="username"
                  required
                />
              </Field>
              <Field label="Password">
                <Input
                  type="password"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  placeholder="Your password"
                  autoComplete="current-password"
                  required
                />
              </Field>
              <Button className="w-full" disabled={loading}>
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
                Sign in
              </Button>
              <p className="text-center text-sm text-slate-600">
                New to Commute OS?{" "}
                <button type="button" className="font-medium text-teal-700 hover:underline" onClick={() => switchMode("signup")}>
                  Create an account
                </button>
              </p>
            </form>
          ) : step === "details" ? (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                sendOtp();
              }}
            >
              <Field label="Full name (optional)">
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Asha Verma" autoComplete="name" />
              </Field>
              <Field label="Email">
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                />
              </Field>
              <Field label="Mobile number">
                <Input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="98765 43210"
                  autoComplete="tel"
                  required
                />
              </Field>
              <Button className="w-full" disabled={loading}>
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                Send verification code
              </Button>
              <p className="text-center text-sm text-slate-600">
                Already have an account?{" "}
                <button type="button" className="font-medium text-teal-700 hover:underline" onClick={() => switchMode("login")}>
                  Sign in
                </button>
              </p>
            </form>
          ) : step === "otp" ? (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                verifyOtp();
              }}
            >
              {devOtp ? (
                <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-center text-sm text-amber-800">
                  Development code: <span className="font-mono font-semibold tracking-widest">{devOtp}</span>
                </p>
              ) : null}
              <Field label="Verification code">
                <Input
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="6-digit code"
                  inputMode="numeric"
                  className="text-center font-mono text-lg tracking-[0.5em]"
                  required
                />
              </Field>
              <Button className="w-full" disabled={loading || otp.length !== 6}>
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                Verify email
              </Button>
              <div className="flex items-center justify-between text-sm">
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-slate-600 hover:text-slate-950"
                  onClick={() => {
                    setStep("details");
                    setNotice(null);
                    setOtp("");
                  }}
                >
                  <ArrowLeft className="h-3.5 w-3.5" /> Edit details
                </button>
                <button
                  type="button"
                  className="font-medium text-teal-700 hover:underline disabled:cursor-not-allowed disabled:text-slate-400 disabled:no-underline"
                  disabled={resendIn > 0 || loading}
                  onClick={sendOtp}
                >
                  {resendIn > 0 ? `Resend code in ${resendIn}s` : "Resend code"}
                </button>
              </div>
            </form>
          ) : (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                finishSignup();
              }}
            >
              <Field label="New password">
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  autoComplete="new-password"
                  minLength={8}
                  required
                />
              </Field>
              <Field label="Confirm password">
                <Input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Re-enter your password"
                  autoComplete="new-password"
                  required
                />
              </Field>
              {confirmPassword.length > 0 ? (
                <p
                  className={
                    password === confirmPassword
                      ? "flex items-center gap-1.5 text-sm text-teal-700"
                      : "text-sm text-red-600"
                  }
                >
                  {password === confirmPassword ? (
                    <>
                      <CheckCircle2 className="h-4 w-4" /> Passwords match
                    </>
                  ) : (
                    "Passwords do not match yet"
                  )}
                </p>
              ) : null}
              <Button className="w-full" disabled={loading || password.length < 8 || password !== confirmPassword}>
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                Continue
              </Button>
            </form>
          )}
        </div>

        <p className="text-center text-xs text-slate-500">
          Bookings, payments, and disruptions are simulated. By continuing you agree to the prototype terms.
        </p>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      {children}
    </label>
  );
}

function GoogleIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.46a5.52 5.52 0 0 1-2.4 3.62v3h3.88c2.27-2.09 3.58-5.17 3.58-8.81Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.07 7.94-2.91l-3.88-3.01c-1.07.72-2.45 1.15-4.06 1.15-3.13 0-5.78-2.11-6.72-4.95H1.27v3.11A12 12 0 0 0 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.28 14.28a7.21 7.21 0 0 1 0-4.56V6.61H1.27a12 12 0 0 0 0 10.78l4.01-3.11Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.77c1.76 0 3.34.61 4.59 1.8l3.44-3.44A11.98 11.98 0 0 0 1.27 6.61l4.01 3.11C6.22 6.88 8.87 4.77 12 4.77Z"
      />
    </svg>
  );
}
