import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, errorMessage } from '../lib/api';
import { useAuth } from '../lib/auth';
import { cx } from '../lib/cx';
import { addDays, fmtDateTime, fmtDay, fmtTime, HANDOFF_LABEL, istDate, ms } from '../lib/format';
import { useMeta } from '../lib/meta';
import type { Appointment, CallDetail, CallSummary, Doctor } from '../lib/types';
import { Button, Card, DemoBanner, EmptyState, ErrorState, OutcomeBadge, Spinner } from '../components/ui';
import { Logo } from './LoginPage';

type Tab = 'calendar' | 'calls' | 'doctors';
const DOC_COLORS = ['border-l-teal-500 bg-teal-50', 'border-l-violet-500 bg-violet-50', 'border-l-amber-500 bg-amber-50', 'border-l-sky-500 bg-sky-50'];

export function DashboardPage() {
  const { user, signOut } = useAuth();
  const { data: meta } = useMeta();
  const [tab, setTab] = useState<Tab>('calendar');
  const doctors = useQuery({ queryKey: ['doctors'], queryFn: () => api<{ items: Doctor[] }>('/api/doctors') });
  const widgetUrl = `${window.location.origin}/talk/${user!.clinic_slug}`;

  return (
    <div className="min-h-screen">
      <DemoBanner show={!!meta?.demo_mode} />
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-3">
            <Logo />
            <span className="hidden text-sm text-slate-500 sm:inline">· {user!.clinic_name}</span>
          </div>
          <div className="flex items-center gap-2">
            <a href={widgetUrl} target="_blank" rel="noreferrer" className="rounded-lg bg-teal-700 px-3 py-2 text-sm font-medium text-white hover:bg-teal-800">
              Open patient widget ↗
            </a>
            <button type="button" onClick={signOut} className="rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-slate-100">
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        {user!.is_demo && (
          <p className="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-900">
            This is your private demo clinic. Open the patient widget, book an appointment by talking (or typing), then come back: it appears in the calendar and the call log.
          </p>
        )}
        <div role="tablist" aria-label="Dashboard" className="flex gap-1 border-b border-slate-200">
          {(['calendar', 'calls', 'doctors'] as Tab[]).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={cx('-mb-px border-b-2 px-4 py-2 text-sm font-medium capitalize', tab === t ? 'border-teal-700 text-teal-800' : 'border-transparent text-slate-600 hover:text-slate-900')}
            >
              {t === 'calls' ? 'Call log' : t}
            </button>
          ))}
        </div>
        {tab === 'calendar' && <Calendar doctors={doctors.data?.items ?? []} />}
        {tab === 'calls' && <Calls />}
        {tab === 'doctors' && (doctors.isLoading ? <Spinner label="Loading…" /> : doctors.error ? <ErrorState message={errorMessage(doctors.error)} /> : <Doctors items={doctors.data!.items} />)}
      </main>
    </div>
  );
}

function Calendar({ doctors }: { doctors: Doctor[] }) {
  const qc = useQueryClient();
  const [start, setStart] = useState(() => istDate(new Date()));
  const [view, setView] = useState<'day' | 'week'>(() => (typeof window !== 'undefined' && window.innerWidth < 640 ? 'day' : 'week'));
  const days = view === 'week' ? 7 : 1;
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['appointments', start, days],
    queryFn: () => api<{ items: Appointment[] }>(`/api/appointments?from=${start}&days=${days}`),
    refetchInterval: 10_000,
  });
  const cancel = useMutation({
    mutationFn: (id: number) => api<Appointment>(`/api/appointments/${id}/cancel`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['appointments'] }),
  });
  const color = (doctorId: number) => DOC_COLORS[Math.max(0, doctors.findIndex((d) => d.id === doctorId)) % DOC_COLORS.length];
  const dates = Array.from({ length: days }, (_, i) => addDays(start, i));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <Button variant="secondary" onClick={() => setStart(addDays(start, -days))} aria-label="Previous">
            ←
          </Button>
          <Button variant="secondary" onClick={() => setStart(istDate(new Date()))}>
            Today
          </Button>
          <Button variant="secondary" onClick={() => setStart(addDays(start, days))} aria-label="Next">
            →
          </Button>
        </div>
        <div role="group" aria-label="View" className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5 text-sm">
          {(['day', 'week'] as const).map((v) => (
            <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)} className={cx('rounded-md px-3 py-1 capitalize', view === v ? 'bg-teal-700 text-white' : 'text-slate-700')}>
              {v}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-3 text-xs text-slate-600">
        {doctors.map((d) => (
          <span key={d.id} className={cx('rounded border-l-4 px-2 py-0.5', color(d.id))}>
            {d.name} · {d.specialty}
          </span>
        ))}
      </div>
      {isLoading ? (
        <Spinner label="Loading…" />
      ) : error ? (
        <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
      ) : (
        <div className={cx('grid gap-3', view === 'week' ? 'sm:grid-cols-2 lg:grid-cols-7' : '')}>
          {dates.map((d) => {
            const items = data!.items.filter((a) => istDate(new Date(a.starts_at)) === d);
            return (
              <Card key={d} className="p-3 sm:p-3">
                <h3 className="text-sm font-semibold text-slate-700">{fmtDay(`${d}T12:00:00+05:30`)}</h3>
                {items.length === 0 ? (
                  <p className="mt-2 text-xs text-slate-400">No bookings</p>
                ) : (
                  <ul className="mt-2 space-y-2">
                    {items.map((a) => (
                      <li key={a.id} className={cx('rounded-md border-l-4 px-2 py-1.5 text-xs', color(a.doctor_id))}>
                        <p className="font-semibold text-slate-900">{fmtTime(a.starts_at)}</p>
                        <p className="text-slate-800">{a.patient_name}</p>
                        <p className="text-slate-500">
                          {a.patient_phone} · {a.source === 'voice' ? '🎙 voice' : a.source}
                        </p>
                        <button type="button" onClick={() => window.confirm(`Cancel ${a.patient_name} at ${fmtTime(a.starts_at)}?`) && cancel.mutate(a.id)} className="mt-1 text-rose-700 hover:underline">
                          Cancel
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Calls() {
  const [open, setOpen] = useState<string | null>(null);
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['calls'], queryFn: () => api<{ items: CallSummary[] }>('/api/calls'), refetchInterval: 10_000 });
  if (isLoading) return <Spinner label="Loading…" />;
  if (error) return <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />;
  if (!data!.items.length) return <EmptyState title="No calls yet">Open the patient widget and start a call.</EmptyState>;
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <ul className="space-y-2 lg:col-span-2" aria-label="Calls">
        {data!.items.map((c) => (
          <li key={c.id}>
            <button
              type="button"
              onClick={() => setOpen(c.id)}
              aria-pressed={open === c.id}
              className={cx('block w-full rounded-xl border bg-white p-3 text-left shadow-sm hover:border-teal-300', open === c.id ? 'border-teal-500' : 'border-slate-200')}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-slate-900">{c.patient_name ?? 'Unknown caller'}</span>
                <OutcomeBadge outcome={c.outcome} />
              </div>
              <p className="mt-0.5 text-xs text-slate-500">
                {fmtDateTime(c.created_at)} · {c.turns} turns · {c.language ?? '—'} · agent avg {ms(c.avg_agent_ms)}
              </p>
              {c.handoff_reason && <p className="mt-1 text-xs text-amber-800">{HANDOFF_LABEL[c.handoff_reason] ?? c.handoff_reason}</p>}
            </button>
          </li>
        ))}
      </ul>
      <div className="lg:col-span-3">{open ? <Transcript id={open} /> : <EmptyState title="Select a call to read its transcript" />}</div>
    </div>
  );
}

function Transcript({ id }: { id: string }) {
  const { data, isLoading, error } = useQuery({ queryKey: ['call', id], queryFn: () => api<CallDetail>(`/api/calls/${id}`) });
  if (isLoading) return <Spinner label="Loading…" />;
  if (error) return <ErrorState message={errorMessage(error)} />;
  const c = data!;
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">Transcript</h3>
        <OutcomeBadge outcome={c.outcome} />
      </div>
      {c.appointment && (
        <p className="mt-1 text-sm text-slate-600">
          {c.appointment.doctor} · {fmtDateTime(c.appointment.starts_at)} ({c.appointment.status})
        </p>
      )}
      <p className="mt-1 text-xs text-slate-500">Phone numbers are masked in stored transcripts. Provider: {c.provider}.</p>
      <ol className="mt-3 space-y-2">
        {c.turns.map((t, i) => (
          <li key={i} className={cx('max-w-[90%] rounded-2xl px-3 py-2 text-sm', t.role === 'agent' ? 'bg-slate-100 text-slate-900' : 'ml-auto bg-teal-700 text-white')}>
            <p>{t.text}</p>
            {(t.agent_ms !== null || t.stt_ms !== null || t.tts_ms !== null) && (
              <p className={cx('mt-1 text-[11px]', t.role === 'agent' ? 'text-slate-500' : 'text-teal-100')}>
                {t.stt_ms !== null && `STT ${ms(t.stt_ms)} · `}
                {t.agent_ms !== null && `agent ${ms(t.agent_ms)}`}
                {t.tts_ms !== null && ` · TTS ${ms(t.tts_ms)}`}
              </p>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}

const DAY_NAMES: [string, string][] = [
  ['mon', 'Mon'],
  ['tue', 'Tue'],
  ['wed', 'Wed'],
  ['thu', 'Thu'],
  ['fri', 'Fri'],
  ['sat', 'Sat'],
  ['sun', 'Sun'],
];

function Doctors({ items }: { items: Doctor[] }) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {items.map((d) => (
        <Card key={d.id}>
          <p className="font-semibold">{d.name}</p>
          <p className="text-sm text-slate-500" lang="hi">
            {d.name_hi} · {d.specialty} ({d.specialty_hi})
          </p>
          <p className="mt-1 text-xs text-slate-500">{d.slot_minutes}-minute slots</p>
          <dl className="mt-3 space-y-1 text-sm">
            {DAY_NAMES.map(([k, label]) => (
              <div key={k} className="flex justify-between gap-2">
                <dt className="text-slate-500">{label}</dt>
                <dd className={d.schedule[k]?.length ? 'text-slate-800' : 'text-slate-400'}>{d.schedule[k]?.length ? d.schedule[k].map(([a, b]) => `${a}–${b}`).join(', ') : 'Off'}</dd>
              </div>
            ))}
          </dl>
        </Card>
      ))}
    </div>
  );
}
