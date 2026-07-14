import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { fetchMyErrands } from "../api/errands";
import { useAuth } from "../stores/auth";
import NotificationBell from "./NotificationBell";

// You're locked into a role while it has work in flight.
const ACTIVE_REQUESTED = ["OPEN", "ACCEPTED", "IN_PROGRESS", "DELIVERED"];
const ACTIVE_RUNNING = ["ACCEPTED", "IN_PROGRESS", "DELIVERED"];

function ModeToggle() {
  const location = useLocation();
  const navigate = useNavigate();
  const onRunner = location.pathname.startsWith("/runner");

  const { data: mine } = useQuery({ queryKey: ["my-errands"], queryFn: fetchMyErrands });
  const activeRequested = (mine?.requested ?? []).some((e) =>
    ACTIVE_REQUESTED.includes(e.status),
  );
  const activeRunning = (mine?.running ?? []).some((e) => ACTIVE_RUNNING.includes(e.status));
  // A live errand (as requester or runner) commits you to that side until it's done.
  const locked = activeRequested || activeRunning;
  const lockHint = locked
    ? "Finish your active errand before switching roles"
    : undefined;

  function go(runner: boolean) {
    if (locked || runner === onRunner) return;
    navigate(runner ? "/runner" : "/");
  }

  const seg = (label: string, isActive: boolean, target: boolean) =>
    isActive ? (
      <span className="rounded-full bg-brand px-3 py-1.5 text-white">{label}</span>
    ) : (
      <button
        onClick={() => go(target)}
        disabled={locked}
        title={lockHint}
        className={`rounded-full px-3 py-1.5 transition ${
          locked ? "cursor-not-allowed text-muted/50" : "text-brand-dark hover:text-brand"
        }`}
      >
        {label}
      </button>
    );

  return (
    <div
      className="flex items-center rounded-full bg-brand-soft p-0.5 text-sm font-bold"
      title={lockHint}
    >
      {seg("🧑 Order", !onRunner, false)}
      {seg("🛵 Run", onRunner, true)}
      {locked && <span className="px-1.5 text-xs">🔒</span>}
    </div>
  );
}

export default function Navbar() {
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <Link to="/" className="flex items-center gap-2">
          <span className="text-2xl">🛵</span>
          <span className="text-xl font-extrabold tracking-tight text-brand">errandly</span>
        </Link>

        <div className="flex items-center gap-3 text-sm">
          {user?.role === "VENDOR" ? (
            <Link
              to="/vendor"
              className="rounded-lg bg-brand-soft px-3 py-1.5 font-bold text-brand-dark transition hover:bg-brand hover:text-white"
            >
              My store
            </Link>
          ) : (
            <>
              <Link
                to="/shops"
                className="hidden rounded-lg px-2 py-1.5 text-xl transition hover:bg-brand-soft sm:block"
                title="Campus stores"
              >
                🏪
              </Link>
              <ModeToggle />
              <Link
                to="/timetable"
                title="My timetable"
                className="hidden rounded-lg px-2 py-1.5 text-xl transition hover:bg-brand-soft sm:block"
              >
                🗓️
              </Link>
            </>
          )}
          <NotificationBell />
          <span className="hidden items-center gap-1 font-medium text-muted sm:flex">
            <svg className="h-4 w-4 text-brand" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M9.69 18.933l.003.001a.75.75 0 00.614 0l.003-.001.018-.008a5.741 5.741 0 00.281-.14c.186-.096.446-.24.757-.433.62-.384 1.445-.966 2.274-1.765C15.302 14.988 17 12.493 17 9.5a7 7 0 10-14 0c0 2.992 1.698 5.487 3.36 7.087a15.1 15.1 0 003.031 2.198l.28.14.018.008zM10 11.25a1.75 1.75 0 100-3.5 1.75 1.75 0 000 3.5z"
                clipRule="evenodd"
              />
            </svg>
            VIT Vellore
          </span>

          {user && (
            <div className="hidden flex-col items-end sm:flex">
              <span className="font-semibold">{user.display_name}</span>
              <span className="text-xs text-muted">
                {user.role === "VENDOR"
                  ? "Store owner"
                  : `★ ${Number(user.reputation_score).toFixed(1)} · ${user.student_id ?? ""}`}
              </span>
            </div>
          )}
          {user?.photo_url ? (
            <img
              src={user.photo_url}
              alt={user.display_name}
              className="h-9 w-9 rounded-full object-cover"
            />
          ) : (
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-soft font-bold text-brand">
              {(user?.display_name ?? "?").charAt(0).toUpperCase()}
            </div>
          )}
          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="rounded-lg border border-line px-3 py-1.5 font-medium text-muted transition hover:border-brand hover:text-brand"
          >
            Logout
          </button>
        </div>
      </div>
    </header>
  );
}
