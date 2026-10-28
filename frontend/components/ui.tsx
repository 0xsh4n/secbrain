import { ReactNode, ButtonHTMLAttributes, InputHTMLAttributes, TextareaHTMLAttributes, SelectHTMLAttributes } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-border bg-surface ${className}`}>{children}</div>
  );
}

export function CardHeader({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-border px-4 py-3">
      <h2 className="text-sm font-semibold tracking-wide text-fg">{title}</h2>
      {action}
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) {
  const styles = {
    primary: "bg-accent-dim text-black hover:bg-accent font-medium",
    ghost: "bg-surface-2 text-fg hover:bg-border",
    danger: "bg-danger/10 text-danger hover:bg-danger/20 border border-danger/40",
  }[variant];
  return (
    <button
      className={`rounded-md px-3 py-1.5 text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${styles} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-fg outline-none focus:border-accent ${props.className || ""}`}
    />
  );
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-fg outline-none focus:border-accent ${props.className || ""}`}
    />
  );
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`w-full rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-fg outline-none focus:border-accent ${props.className || ""}`}
    />
  );
}

const STATUS_COLORS: Record<string, string> = {
  indexed: "bg-success/15 text-success",
  COMPLETED: "bg-success/15 text-success",
  processing: "bg-accent/15 text-accent",
  INDEXING: "bg-accent/15 text-accent",
  FETCHING: "bg-accent/15 text-accent",
  EXTRACTING: "bg-accent/15 text-accent",
  pending: "bg-warn/15 text-warn",
  PENDING: "bg-warn/15 text-warn",
  failed: "bg-danger/15 text-danger",
  FAILED: "bg-danger/15 text-danger",
  CANCELLED: "bg-muted/15 text-muted",
};

export function Badge({ children }: { children: string }) {
  const color = STATUS_COLORS[children] || "bg-surface-2 text-muted";
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${color}`}>
      {children}
    </span>
  );
}

export function Empty({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center text-muted">
      <div className="text-3xl opacity-40">∅</div>
      <p className="text-sm">{message}</p>
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
      {message}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-12 text-muted">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-border border-t-accent" />
    </div>
  );
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Card className="p-4">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-fg">{value}</div>
    </Card>
  );
}
