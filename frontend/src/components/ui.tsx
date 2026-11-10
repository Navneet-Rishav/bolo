import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cx } from '../lib/cx';
import { OUTCOME_LABEL } from '../lib/format';
import type { Outcome } from '../lib/types';

export function Button({
  variant = 'primary',
  loading,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; loading?: boolean }) {
  const styles = {
    primary: 'bg-teal-700 text-white hover:bg-teal-800 disabled:bg-teal-700/50',
    secondary: 'border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 disabled:opacity-50',
    ghost: 'text-slate-700 hover:bg-slate-100 disabled:opacity-50',
    danger: 'border border-rose-200 bg-white text-rose-700 hover:bg-rose-50 disabled:opacity-50',
  }[variant];
  return (
    <button
      className={cx('inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed', styles, className)}
      disabled={rest.disabled || loading}
      {...rest}
    >
      {loading && <Spinner small />}
      {children}
    </button>
  );
}

export function Spinner({ small, label }: { small?: boolean; label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-slate-500">
      <span className={cx('animate-spin rounded-full border-2 border-current border-t-transparent', small ? 'h-3.5 w-3.5' : 'h-5 w-5')} aria-hidden="true" />
      {label ? <span>{label}</span> : <span className="sr-only">Loading</span>}
    </span>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx('rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5', className)}>{children}</div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
      <p>{message}</p>
      {onRetry && (
        <Button variant="secondary" className="mt-3" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
      <p className="font-medium text-slate-800">{title}</p>
      {children && <div className="mt-1 text-sm text-slate-500">{children}</div>}
    </div>
  );
}

const OUTCOME_STYLE: Record<Outcome, string> = {
  in_progress: 'bg-sky-100 text-sky-800',
  booked: 'bg-emerald-100 text-emerald-800',
  rescheduled: 'bg-teal-100 text-teal-800',
  cancelled: 'bg-slate-200 text-slate-700',
  handoff: 'bg-amber-100 text-amber-900',
  ended: 'bg-slate-100 text-slate-600',
};

export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  return <span className={cx('inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap', OUTCOME_STYLE[outcome])}>{OUTCOME_LABEL[outcome]}</span>;
}

export function DemoBanner({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-xs text-amber-900 sm:text-sm" role="note">
      Demo mode: replies come from simple keyword rules, not an AI model, and voice is off (it needs the Sarvam API). Type to talk to the receptionist.
    </div>
  );
}
