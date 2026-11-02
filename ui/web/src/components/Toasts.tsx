import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

/** A follow-up the toast offers, such as Undo after a delete. */
export type ToastAction = { label: string; run: () => void };

type Toast = { id: number; message: string; action?: ToastAction };

type Show = (message: string, action?: ToastAction) => void;

const ToastContext = createContext<Show>(() => {});

export const useToast = () => useContext(ToastContext);

const VISIBLE_MS = 4000;
/** A toast with an action stays longer, so there is time to reach it. */
const ACTION_MS = 7000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);
  const stack = useRef<HTMLDivElement>(null);

  // A modal dialog sits in the browser's top layer, above everything else on the page.
  // Re-showing this popover whenever a toast arrives puts the toasts above the dialog.
  useEffect(() => {
    const element = stack.current;
    if (!element || !toasts.length) return;
    if (element.matches(":popover-open")) element.hidePopover();
    element.showPopover();
  }, [toasts.length]);

  const dismiss = useCallback((id: number) => setToasts((current) => current.filter((toast) => toast.id !== id)), []);

  const show = useCallback<Show>(
    (message, action) => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, message, action }]);
      setTimeout(() => dismiss(id), action ? ACTION_MS : VISIBLE_MS);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="lv-toasts" ref={stack} popover="manual" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div className="lv-toast" key={toast.id}>
            <span>{toast.message}</span>
            {toast.action && (
              <button
                className="ll-link-button"
                type="button"
                onClick={() => {
                  dismiss(toast.id);
                  toast.action!.run();
                }}
              >
                {toast.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
