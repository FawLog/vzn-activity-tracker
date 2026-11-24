import { AlertTriangle, Database } from "lucide-react";
import type { ReactNode } from "react";

export function LoadingState({ label = "Loading records" }: { label?: string }) {
  return (
    <div className="loading-state" role="status">
      <span className="loading-state__line" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="error-state" role="alert">
      <AlertTriangle size={20} />
      <div>
        <strong>Unable to load this view</strong>
        <p>{message}</p>
        {action}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  compact = false,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={`empty-state${compact ? " empty-state--compact" : ""}`}>
      <Database aria-hidden="true" />
      <strong>{title}</strong>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "success" | "error"; children: ReactNode }) {
  return <div className={`notice notice--${tone}`}>{children}</div>;
}
