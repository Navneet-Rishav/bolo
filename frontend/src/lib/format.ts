import type { Outcome } from './types';

/** All times are shown in the clinic's time zone (IST), whatever the viewer's browser is set to. */
export const TZ = 'Asia/Kolkata';

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', timeZone: TZ });
}

export function fmtDay(iso: string): string {
  return new Date(iso).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', timeZone: TZ });
}

export function fmtDateTime(iso: string): string {
  return `${fmtDay(iso)}, ${fmtTime(iso)}`;
}

/** YYYY-MM-DD of an instant in IST. */
export function istDate(d: Date): string {
  return d.toLocaleDateString('en-CA', { timeZone: TZ });
}

export function addDays(ymd: string, n: number): string {
  const [y, m, d] = ymd.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + n));
  return dt.toISOString().slice(0, 10);
}

export const OUTCOME_LABEL: Record<Outcome, string> = {
  in_progress: 'In progress',
  booked: 'Booked',
  rescheduled: 'Rescheduled',
  cancelled: 'Cancelled',
  handoff: 'Needs staff',
  ended: 'No change',
};

export const HANDOFF_LABEL: Record<string, string> = {
  emergency: 'Emergency: told to call 112',
  human_requested: 'Asked for a person',
  not_understood: 'Not understood after 3 tries',
  no_slots: 'No free slots in 2 weeks',
};

export function ms(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`;
}
