import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { fetchMyErrands } from "../api/errands";
import { fetchWallet } from "../api/ledger";
import { useAuth } from "../stores/auth";
import NotificationBell from "./NotificationBell";

function WalletChip() {
  const { data } = useQuery({ queryKey: ["wallet"], queryFn: fetchWallet });
  return (
    <Link
      to="/wallet"
      title="Wallet & escrow"
      className="flex items-center gap-1.5 rounded-full bg-brand-soft px-3 py-1.5 font-bold text-brand-dark transition hover:bg-brand hover:text-white"
    >
      <span>👛</span>
      <span>₹{Number(data?.balance ?? 0).toFixed(0)}</span>
    </Link>
  );
}

// A run you've taken on (accepted or mid-delivery) is the only thing that
// commits you — everything else, including any order you've placed, leaves you
// free to switch. Delivered runs are already handed off, so they don't count.
const ACTIVE_RUN = ["ACCEPTED", "IN_PROGRESS"];

function ModeToggle() {
  const location = useLocation();
  const navigate = useNavigate();
  const onRunner = location.pathname.startsWith("/runner");

  const { data: mine } = useQuery({ queryKey: ["my-errands"], queryFn: fetchMyErrands });
  // Directional lock: you can always jump INTO run mode. You just can't leave
  // it back to Order while a delivery you accepted is still on you — so nobody
  // gets ghosted mid-run. Placing/receiving an order never locks anything.
  const onActiveRun = (mine?.running ?? []).some((e) => ACTIVE_RUN.includes(e.status));
  const lockLeaveRunner = onRunner && onActiveRun;
  const lockHint = lockLeaveRunner
    ? "Finish the run you're on before switching back to Order"
    : undefined;

  function go(runner: boolean) {
    if (runner === onRunner) return;
    if (!runner && lockLeaveRunner) return; // leaving Run mode mid-delivery
    navigate(runner ? "/runner" : "/");
  }

  const seg = (label: string, isActive: boolean, target: boolean) => {
    if (isActive) {
      return <span className="rounded-full bg-brand px-3 py-1.5 text-white">{label}</span>;
    }
    // Only the Order segment (target === false) is ever disabled, and only
    // while you're mid-run on the runner page.
    const disabled = target === false && lockLeaveRunner;
    return (
      <button
        onClick={() => go(target)}
        disabled={disabled}
        title={disabled ? lockHint : undefined}
        className={`rounded-full px-3 py-1.5 transition ${
          disabled ? "cursor-not-allowed text-muted/50" : "text-brand-dark hover:text-brand"
        }`}
      >
        {label}
      </button>
    );
  };

  return (
    <div className="flex items-center rounded-full bg-brand-soft p-0.5 text-sm font-bold">
      {seg("🧑 Order", !onRunner, false)}
      {seg("🛵 Run", onRunner, true)}
      {lockLeaveRunner && (
        <span className="px-1.5 text-xs" title={lockHint}>
          🔒
        </span>
      )}
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
            <ModeToggle />
          )}
          {user?.role !== "VENDOR" && <WalletChip />}
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
          <Link to="/profile" title="Profile, history & settings" className="shrink-0">
            {user?.photo_url ? (
              <img
                src={user.photo_url}
                alt={user.display_name}
                className="h-9 w-9 rounded-full object-cover ring-2 ring-transparent transition hover:ring-brand"
              />
            ) : (
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-soft font-bold text-brand ring-2 ring-transparent transition hover:ring-brand">
                {(user?.display_name ?? "?").charAt(0).toUpperCase()}
              </div>
            )}
          </Link>
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
