import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api, ApiError, errorMessage } from '../lib/api';
import { useAuth } from '../lib/auth';
import { useMeta } from '../lib/meta';
import type { Session } from '../lib/types';
import { Button, Card, DemoBanner } from '../components/ui';

export function Logo() {
  return (
    <span className="inline-flex items-center gap-2 font-semibold text-slate-900">
      <img src="/favicon.svg" alt="" className="h-7 w-7" />
      Bolo <span className="font-normal text-slate-500">बोलो</span>
    </span>
  );
}

export function LoginPage() {
  const { signIn } = useAuth();
  const { data: meta } = useMeta();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [form, setForm] = useState({ clinic_name: '', name: '', email: '', password: '' });
  const demo = useMutation({ mutationFn: () => api<Session>('/api/auth/demo', { method: 'POST', auth: false }), onSuccess: signIn });
  const submit = useMutation({
    mutationFn: () => api<Session>(`/api/auth/${mode}`, { auth: false, body: mode === 'login' ? { email: form.email, password: form.password } : form }),
    onSuccess: signIn,
  });
  const fieldErrors: Record<string, string> = {};
  if (submit.error instanceof ApiError && Array.isArray(submit.error.details)) {
    for (const d of submit.error.details as { field: string; message: string }[]) fieldErrors[d.field] = d.message;
  }
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit.mutate();
  };

  return (
    <div className="min-h-screen">
      <DemoBanner show={!!meta?.demo_mode} />
      <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10">
        <Logo />
        <div>
          <h1 className="text-2xl font-semibold">A Hinglish voice receptionist for clinics</h1>
          <p className="mt-2 text-slate-600">
            Patients book, reschedule or cancel appointments by talking in Hindi, English or Hinglish. Staff see the calendar and every call's transcript.
          </p>
        </div>
        <Card>
          <Button className="w-full" onClick={() => demo.mutate()} loading={demo.isPending}>
            Try the demo
          </Button>
          <p className="mt-2 text-center text-xs text-slate-500">You get your own fictional clinic with three doctors, a staff dashboard and a patient widget. No sign-up.</p>
          {demo.isPending && <p className="mt-2 text-center text-xs text-slate-500">The free-tier server may take up to a minute to wake up.</p>}
          {demo.error && (
            <p className="mt-2 text-sm text-rose-700" role="alert">
              {errorMessage(demo.error)}
            </p>
          )}
        </Card>
        <Card>
          <form onSubmit={onSubmit} className="space-y-3" noValidate>
            <h2 className="text-lg font-semibold">{mode === 'login' ? 'Staff login' : 'Register your clinic'}</h2>
            {mode === 'register' && (
              <>
                <Input id="clinic_name" label="Clinic name" value={form.clinic_name} onChange={set('clinic_name')} error={fieldErrors.clinic_name} />
                <Input id="name" label="Your name" value={form.name} onChange={set('name')} error={fieldErrors.name} autoComplete="name" />
              </>
            )}
            <Input id="email" label="Email" type="email" value={form.email} onChange={set('email')} error={fieldErrors.email} autoComplete="email" />
            <Input id="password" label="Password" type="password" value={form.password} onChange={set('password')} error={fieldErrors.password} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
            {submit.error && !Object.keys(fieldErrors).length && (
              <p className="text-sm text-rose-700" role="alert">
                {errorMessage(submit.error)}
              </p>
            )}
            <Button type="submit" variant="secondary" className="w-full" loading={submit.isPending}>
              {mode === 'login' ? 'Log in' : 'Create clinic'}
            </Button>
            <button type="button" className="w-full text-center text-sm text-teal-800 hover:underline" onClick={() => (setMode(mode === 'login' ? 'register' : 'login'), submit.reset())}>
              {mode === 'login' ? 'New clinic? Register' : 'Already registered? Log in'}
            </button>
          </form>
        </Card>
      </div>
    </div>
  );
}

function Input({ id, label, error, ...rest }: React.InputHTMLAttributes<HTMLInputElement> & { id: string; label: string; error?: string }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        name={id}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : undefined}
        className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-600 focus:ring-0"
        {...rest}
      />
      {error && (
        <p id={`${id}-error`} className="mt-1 text-xs text-rose-700">
          {error}
        </p>
      )}
    </div>
  );
}
