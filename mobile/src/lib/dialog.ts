/**
 * In-app dialogs.
 *
 * Neither platform default was acceptable. `Alert` is a no-op in
 * react-native-web, so confirmations silently never resolved and the action
 * behind them looked broken; `window.alert`/`confirm` render as a bar dropping
 * from the top of the browser chrome, which reads as the browser interrupting
 * you rather than the app asking you something. And on a device the OS alert
 * carries none of the app's design.
 *
 * So dialogs are drawn by the app itself — see DialogHost, mounted once at the
 * root. This module stays a plain imperative API on purpose: `notify()` and
 * `confirm()` are called from event handlers and catch blocks all over the
 * codebase, most of them nowhere near a React component, and none of them
 * should need a hook or a context to ask a question.
 */

export interface DialogRequest {
  id: number;
  title: string;
  message?: string;
  confirmLabel: string;
  cancelLabel?: string; // absent → single-button notice
  destructive: boolean;
  resolve: (ok: boolean) => void;
}

type Listener = (dialog: DialogRequest | null) => void;

let listener: Listener | null = null;
let queue: DialogRequest[] = [];
let current: DialogRequest | null = null;
let nextId = 1;

/** Called by DialogHost. Only one host is expected. */
export function subscribeToDialogs(fn: Listener): () => void {
  listener = fn;
  fn(current);
  return () => {
    listener = null;
  };
}

function pump() {
  if (current || !queue.length) return;
  current = queue.shift() ?? null;
  listener?.(current);
}

/** Resolve the visible dialog and show the next one, if any. */
export function resolveDialog(ok: boolean) {
  const active = current;
  current = null;
  active?.resolve(ok);
  listener?.(null);
  // Let the close animation start before the next one opens.
  setTimeout(pump, 120);
}

function push(req: Omit<DialogRequest, "id">): void {
  queue.push({ ...req, id: nextId++ });
  pump();
}

/** Tell the user something. No decision required. */
export function notify(title: string, message?: string): Promise<boolean> {
  return new Promise((resolve) => {
    push({ title, message, confirmLabel: "Got it", destructive: false, resolve });
  });
}

/** Ask the user to confirm. Resolves true if they went ahead. */
export function confirm(
  title: string,
  message?: string,
  options?: { confirmLabel?: string; cancelLabel?: string; destructive?: boolean },
): Promise<boolean> {
  return new Promise((resolve) => {
    push({
      title,
      message,
      confirmLabel: options?.confirmLabel ?? "Confirm",
      cancelLabel: options?.cancelLabel ?? "Cancel",
      destructive: options?.destructive ?? false,
      resolve,
    });
  });
}
