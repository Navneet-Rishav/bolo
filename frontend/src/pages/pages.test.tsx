import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { Providers } from '../App';
import { TalkPage } from './TalkPage';
import { DashboardPage } from './DashboardPage';
import { addDays, fmtTime, istDate } from '../lib/format';

const META = { provider: 'demo', model: 'rule-based (no AI)', demo_mode: true, voice_enabled: false, timezone: 'Asia/Kolkata' };
const CLINIC = { name: 'Sehat Demo Clinic', is_demo: true, voice_enabled: false, demo_mode: true, doctors: [{ name: 'Dr. Meera Sharma', name_hi: 'डॉ. मीरा शर्मा', specialty: 'General physician', specialty_hi: 'सामान्य चिकित्सक' }] };
const today = istDate(new Date());

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }));
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      if (path === '/api/meta') return json(META);
      if (path === '/api/public/clinics/abc') return json(CLINIC);
      if (path === '/api/public/clinics/abc/calls') return json({ call_id: 'c1', reply: 'Namaste! Aapka naam bataiye?', audio_b64: null, tts_ms: null, stage: 'identify' }, 201);
      if (path === '/api/public/calls/c1/turns') {
        const t = JSON.parse(String(init?.body)).text as string;
        return json({ transcript: t, reply: 'Shukriya Ravi ji. Aapka 10 digit mobile number bataiye?', stage: 'identify', outcome: 'in_progress', done: false, latency: { stt_ms: null, agent_ms: 12, tts_ms: null }, audio_b64: null });
      }
      if (path === '/api/doctors') return json({ items: [{ id: 1, name: 'Dr. Meera Sharma', name_hi: 'डॉ. मीरा शर्मा', specialty: 'General physician', specialty_hi: 'सामान्य चिकित्सक', slot_minutes: 15, schedule: { mon: [['10:00', '13:00']] } }] });
      if (path === '/api/appointments')
        return json({ items: [{ id: 7, doctor_id: 1, doctor_name: 'Dr. Meera Sharma', patient_name: 'Asha Verma', patient_phone: '******3210', starts_at: `${today}T17:00:00+05:30`, ends_at: `${today}T17:15:00+05:30`, status: 'booked', source: 'voice', call_id: 'c1' }] });
      if (path === '/api/calls') return json({ items: [{ id: 'c1', created_at: `${today}T09:00:00+05:30`, outcome: 'booked', handoff_reason: null, language: 'hinglish', provider: 'demo', turns: 4, patient_name: 'Asha Verma', avg_agent_ms: 9 }] });
      if (path === '/api/calls/c1')
        return json({ id: 'c1', created_at: `${today}T09:00:00+05:30`, outcome: 'booked', handoff_reason: null, language: 'hinglish', provider: 'demo', appointment: null, turns: [{ role: 'patient', text: 'mera number <PHONE> hai', stage: 'identify', stt_ms: null, agent_ms: null, tts_ms: null }] });
      return json({ error: { code: 'not_found', message: 'nope' } }, 404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe('format', () => {
  it('shows times in IST and steps dates', () => {
    expect(fmtTime('2026-11-16T11:30:00Z')).toMatch(/5:00\s?pm/i);
    expect(addDays('2026-11-30', 1)).toBe('2026-12-01');
  });
});

describe('TalkPage', () => {
  it('runs a typed conversation, shows agent latency and disables voice in demo mode', async () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/talk/abc']}>
          <Routes>
            <Route path="/talk/:slug" element={<TalkPage />} />
          </Routes>
        </MemoryRouter>
      </Providers>,
    );
    expect(await screen.findByText(/Demo mode: replies come from simple keyword rules/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Start chat' }));
    expect(await screen.findByText('Namaste! Aapka naam bataiye?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Voice needs the Sarvam API/ })).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Your message'), 'Mera naam Ravi hai{Enter}');
    expect(await screen.findByText(/mobile number bataiye/)).toBeInTheDocument();
    expect(screen.getByText('agent 12 ms')).toBeInTheDocument();
  });
});

describe('DashboardPage', () => {
  it('shows bookings with masked phones and a call transcript', async () => {
    const user = { id: 'u', name: 'Demo', email: 'demo@bolo.demo', is_demo: true, clinic_id: 'k', clinic_name: 'Sehat Demo Clinic', clinic_slug: 'abc' };
    render(
      <Providers initialUser={user}>
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </Providers>,
    );
    expect(await screen.findByText('Asha Verma')).toBeInTheDocument();
    expect(screen.getByText(/\*\*\*\*\*\*3210/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open patient widget/ })).toHaveAttribute('href', expect.stringContaining('/talk/abc'));
    await userEvent.click(screen.getByRole('tab', { name: 'Call log' }));
    await userEvent.click(await screen.findByRole('button', { name: /Asha Verma/ }));
    const transcript = await screen.findByText('Transcript');
    expect(within(transcript.closest('div')!.parentElement!).getByText('mera number <PHONE> hai')).toBeInTheDocument();
  });
});
