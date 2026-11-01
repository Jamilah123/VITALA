import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { ApiError, errorMessage } from "../api/errors";
import { Icon } from "./Icon";

export function Loading({ label = "جارٍ التحميل…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  action,
}: {
  error: unknown;
  onRetry?: () => void;
  action?: ReactNode;
}) {
  const retryable = !(error instanceof ApiError) || error.kind !== "not_found";
  return (
    <div className="error-state" role="alert">
      <div className="error-state__text">
        <Icon name="alert" size={20} />
        <span>{errorMessage(error)}</span>
      </div>
      <div className="error-state__actions">
        {onRetry && retryable && (
          <button type="button" className="btn btn--outline btn--small" onClick={onRetry}>
            إعادة المحاولة
          </button>
        )}
        {action}
      </div>
    </div>
  );
}

export function FormError({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <p className="form-error" role="alert">
      {message}
    </p>
  );
}

export type SourceKind = "live" | "browser" | "demo";

const SOURCE_LABELS: Record<SourceKind, string> = {
  live: "من الخادم",
  browser: "في هذا المتصفح فقط",
  demo: "بيانات تجريبية",
};

export function SourceBadge({ kind }: { kind: SourceKind }) {
  return <span className={`source-badge source-badge--${kind}`}>{SOURCE_LABELS[kind]}</span>;
}

/** Shown on every screen whose content is invented. */
export function DemoNotice({ children }: { children?: ReactNode }) {
  return (
    <aside className="demo-notice" aria-label="تنبيه بيانات تجريبية">
      <strong>عرض تجريبي</strong>
      <span>{children ?? "بيانات لشخصية افتراضية (نورة)، وليست من ملفك وليست توصية طبية."}</span>
    </aside>
  );
}

export function SyntheticDataNotice() {
  return <p className="note note--warn">نسخة للتجربة بلا تسجيل دخول: استخدمي بيانات اصطناعية فقط، ولا تدخلي معلوماتك الصحية الحقيقية.</p>;
}

const ToastContext = createContext<(message: string) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const show = useCallback((text: string) => {
    setMessage(text);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setMessage(null), 5000);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {message && <div className="toast">{message}</div>}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
