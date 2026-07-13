import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { fetchMe, register, resendOtp, verifyEmail } from "../api/auth";
import AuthLayout from "../components/AuthLayout";
import { apiErrorMessage } from "../lib/api";
import { useAuth } from "../stores/auth";

const inputCls =
  "w-full rounded-xl border border-line px-4 py-3 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20";

export default function Register() {
  const [form, setForm] = useState({
    display_name: "",
    student_id: "",
    email: "",
    phone: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Two-step: fill the form, then verify the emailed code.
  const [stage, setStage] = useState<"form" | "verify">("form");
  const [code, setCode] = useState("");
  const [devOtp, setDevOtp] = useState<string | null>(null);
  const [resent, setResent] = useState(false);

  const setTokens = useAuth((s) => s.setTokens);
  const setUser = useAuth((s) => s.setUser);
  const navigate = useNavigate();

  function set(field: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [field]: e.target.value }));
  }

  async function onRegister(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const { devOtp } = await register({ ...form, phone: form.phone || undefined });
      setDevOtp(devOtp);
      if (devOtp) setCode(devOtp); // dev mode: prefill so testing is one click
      setStage("verify");
    } catch (err) {
      setError(apiErrorMessage(err, "Registration failed."));
    } finally {
      setBusy(false);
    }
  }

  async function onVerify(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const tokens = await verifyEmail(form.email, code.trim());
      setTokens(tokens.access_token, tokens.refresh_token);
      setUser(await fetchMe());
      navigate("/", { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err, "Verification failed."));
    } finally {
      setBusy(false);
    }
  }

  async function onResend() {
    setError(null);
    setResent(false);
    try {
      const otp = await resendOtp(form.email);
      setDevOtp(otp);
      if (otp) setCode(otp);
      setResent(true);
    } catch (err) {
      setError(apiErrorMessage(err, "Could not resend the code."));
    }
  }

  if (stage === "verify") {
    return (
      <AuthLayout>
        <div className="text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-brand-soft text-3xl">
            📧
          </div>
          <h2 className="mt-6 text-3xl font-extrabold">Check your email</h2>
          <p className="mt-3 text-muted">
            We sent a 6-digit code to <strong>{form.email}</strong>. Enter it below to activate your
            account — this is how we keep Errandly student-only.
          </p>
        </div>

        {devOtp && (
          <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-center text-sm text-amber-800">
            Dev mode (no email configured): your code is{" "}
            <span className="font-mono font-bold">{devOtp}</span>
          </div>
        )}
        {error && (
          <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={onVerify} className="mt-6 space-y-4">
          <input
            inputMode="numeric"
            autoFocus
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="6-digit code"
            maxLength={8}
            className={`${inputCls} text-center text-2xl font-bold tracking-[0.4em]`}
          />
          <button
            type="submit"
            disabled={busy || code.trim().length < 4}
            className="w-full rounded-xl bg-brand py-3.5 font-bold text-white transition hover:bg-brand-dark disabled:opacity-60"
          >
            {busy ? "Verifying…" : "Verify & continue"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-muted">
          Didn't get it?{" "}
          <button onClick={onResend} className="font-semibold text-brand hover:underline">
            Resend code
          </button>
          {resent && <span className="ml-2 text-green-600">Sent ✓</span>}
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <h2 className="text-3xl font-extrabold">Create your account</h2>
      <p className="mt-2 text-muted">Students only — verified via your university email.</p>

      {error && (
        <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <form onSubmit={onRegister} className="mt-8 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="display_name" className="mb-1.5 block text-sm font-semibold">
              Full name
            </label>
            <input
              id="display_name"
              required
              value={form.display_name}
              onChange={set("display_name")}
              placeholder="Chris Martin"
              className={inputCls}
            />
          </div>
          <div>
            <label htmlFor="student_id" className="mb-1.5 block text-sm font-semibold">
              Student ID
            </label>
            <input
              id="student_id"
              required
              value={form.student_id}
              onChange={set("student_id")}
              placeholder="23BCE0743"
              className={inputCls}
            />
          </div>
        </div>
        <div>
          <label htmlFor="email" className="mb-1.5 block text-sm font-semibold">
            University email
          </label>
          <input
            id="email"
            type="email"
            required
            value={form.email}
            onChange={set("email")}
            placeholder="you@vitstudent.ac.in"
            className={inputCls}
          />
        </div>
        <div>
          <label htmlFor="phone" className="mb-1.5 block text-sm font-semibold">
            Phone <span className="font-normal text-muted">(optional)</span>
          </label>
          <input
            id="phone"
            value={form.phone}
            onChange={set("phone")}
            placeholder="+91 98765 43210"
            className={inputCls}
          />
        </div>
        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm font-semibold">
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            minLength={8}
            value={form.password}
            onChange={set("password")}
            placeholder="At least 8 characters"
            className={inputCls}
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-xl bg-brand py-3.5 font-bold text-white transition hover:bg-brand-dark disabled:opacity-60"
        >
          {busy ? "Creating account…" : "Sign up"}
        </button>
      </form>

      <p className="mt-8 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link to="/login" className="font-semibold text-brand hover:underline">
          Log in
        </Link>
      </p>
    </AuthLayout>
  );
}
