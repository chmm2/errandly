import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { register } from "../api/auth";
import AuthLayout from "../components/AuthLayout";
import { apiErrorMessage } from "../lib/api";

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
  const [submitted, setSubmitted] = useState(false);

  function set(field: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [field]: e.target.value }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await register({ ...form, phone: form.phone || undefined });
      setSubmitted(true);
    } catch (err) {
      setError(apiErrorMessage(err, "Registration failed."));
    } finally {
      setBusy(false);
    }
  }

  if (submitted) {
    return (
      <AuthLayout>
        <div className="text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-brand-soft text-3xl">
            ⏳
          </div>
          <h2 className="mt-6 text-3xl font-extrabold">You're almost in</h2>
          <p className="mt-3 text-muted">
            Your account was created and is <strong>pending verification</strong>. An administrator
            confirms you're a registered student before you can start posting or running errands —
            that's what keeps Errandly student-only.
          </p>
          <Link
            to="/login"
            className="mt-8 inline-block rounded-xl bg-brand px-8 py-3.5 font-bold text-white transition hover:bg-brand-dark"
          >
            Back to login
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <h2 className="text-3xl font-extrabold">Create your account</h2>
      <p className="mt-2 text-muted">Students only — verified against your university registry.</p>

      {error && (
        <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <form onSubmit={onSubmit} className="mt-8 space-y-4">
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
