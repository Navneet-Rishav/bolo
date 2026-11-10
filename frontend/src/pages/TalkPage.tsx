import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api, ApiError, errorMessage } from '../lib/api';
import { cx } from '../lib/cx';
import { ms } from '../lib/format';
import type { ClinicInfo, TurnResponse } from '../lib/types';
import { Button, Card, DemoBanner, ErrorState, Spinner } from '../components/ui';
import { Logo } from './LoginPage';

interface Line {
  role: 'patient' | 'agent';
  text: string;
  latency?: TurnResponse['latency'];
}

const EXAMPLES = ['Mera naam Ravi Kumar hai', '98765 12345', 'Kal Dr Sharma ko dikhana hai, shaam 5 baje', 'haan'];

function play(b64: string | null) {
  if (!b64) return;
  const audio = new Audio(`data:audio/wav;base64,${b64}`);
  void audio.play().catch(() => {});
}

export function TalkPage() {
  const { slug } = useParams<{ slug: string }>();
  const info = useQuery({ queryKey: ['clinic', slug], queryFn: () => api<ClinicInfo>(`/api/public/clinics/${slug}`, { auth: false }) });
  const [callId, setCallId] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [done, setDone] = useState(false);
  const [text, setText] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const voice = !!info.data?.voice_enabled;

  // Braces matter: an effect must return nothing or a cleanup function, not scrollIntoView's return value.
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' });
  }, [lines]);

  const start = useMutation({
    mutationFn: () => api<{ call_id: string; reply: string; audio_b64: string | null; tts_ms: number | null }>(`/api/public/clinics/${slug}/calls`, { auth: false, body: { audio: voice } }),
    onSuccess: (r) => {
      setCallId(r.call_id);
      setDone(false);
      setLines([{ role: 'agent', text: r.reply, latency: { stt_ms: null, agent_ms: null, tts_ms: r.tts_ms } }]);
      play(r.audio_b64);
    },
  });
  const onTurn = (r: TurnResponse) => {
    setLines((ls) => [...ls, { role: 'patient', text: r.transcript }, { role: 'agent', text: r.reply, latency: r.latency }]);
    setDone(r.done);
    play(r.audio_b64);
  };
  const say = useMutation({
    mutationFn: (t: string) => api<TurnResponse>(`/api/public/calls/${callId}/turns`, { auth: false, body: { text: t, audio: voice } }),
    onSuccess: onTurn,
  });
  const voiceTurn = useMutation({
    mutationFn: (blob: Blob) => {
      const form = new FormData();
      form.append('audio', blob, 'turn.webm');
      form.append('reply_audio', 'true');
      return api<TurnResponse>(`/api/public/calls/${callId}/voice-turns`, { auth: false, form });
    },
    onSuccess: onTurn,
  });

  const send = (t: string) => {
    const v = t.trim();
    if (!v || !callId || say.isPending) return;
    setText('');
    say.mutate(v);
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    send(text);
  };
  const busy = say.isPending || voiceTurn.isPending;
  const err = say.error ?? voiceTurn.error ?? start.error;

  if (info.isLoading) return <div className="p-8"><Spinner label="Loading…" /></div>;
  if (info.error)
    return (
      <div className="mx-auto max-w-md p-6">
        <ErrorState message={info.error instanceof ApiError && info.error.status === 404 ? 'This clinic link is not valid (demo clinics expire after 24 hours).' : errorMessage(info.error)} />
      </div>
    );
  const clinic = info.data!;

  return (
    <div className="flex min-h-screen flex-col">
      <DemoBanner show={clinic.demo_mode} />
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-3">
          <Logo />
          <span className="text-sm text-slate-600">{clinic.name}</span>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-4 px-4 py-6">
        {!callId ? (
          <Card className="text-center">
            <h1 className="text-xl font-semibold">Talk to the receptionist</h1>
            <p className="mt-1 text-sm text-slate-600">Book, reschedule or cancel an appointment in Hindi, English or Hinglish.</p>
            <ul className="mt-3 flex flex-wrap justify-center gap-2 text-xs text-slate-600">
              {clinic.doctors.map((d) => (
                <li key={d.name} className="rounded-full bg-slate-100 px-2.5 py-1">
                  {d.name} · {d.specialty}
                </li>
              ))}
            </ul>
            <Button className="mt-4" onClick={() => start.mutate()} loading={start.isPending}>
              {voice ? '📞 Start call' : 'Start chat'}
            </Button>
          </Card>
        ) : (
          <>
            <ol className="flex-1 space-y-3" aria-live="polite" aria-label="Conversation">
              {lines.map((l, i) => (
                <li key={i} className={cx('max-w-[85%] rounded-2xl px-3 py-2 text-sm', l.role === 'agent' ? 'rounded-bl-sm bg-white text-slate-900 shadow-sm' : 'ml-auto rounded-br-sm bg-teal-700 text-white')}>
                  <p>{l.text}</p>
                  {l.role === 'agent' && l.latency && (l.latency.agent_ms !== null || l.latency.tts_ms !== null) && (
                    <p className="mt-1 text-[11px] text-slate-500">
                      {l.latency.stt_ms !== null && `STT ${ms(l.latency.stt_ms)} · `}
                      {l.latency.agent_ms !== null && `agent ${ms(l.latency.agent_ms)}`}
                      {l.latency.tts_ms !== null && ` · TTS ${ms(l.latency.tts_ms)}`}
                    </p>
                  )}
                </li>
              ))}
              {busy && (
                <li>
                  <Spinner small label="…" />
                </li>
              )}
              <div ref={endRef} />
            </ol>
            {err && <ErrorState message={errorMessage(err)} />}
            {done ? (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white p-3 text-sm">
                <span className="text-slate-600">Call ended.</span>
                <Button variant="secondary" onClick={() => start.mutate()}>
                  New call
                </Button>
              </div>
            ) : (
              <>
                {lines.length <= 2 && !voice && (
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className="text-slate-500">Try:</span>
                    {EXAMPLES.map((e) => (
                      <button key={e} type="button" onClick={() => setText(e)} className="rounded-full border border-slate-300 bg-white px-2.5 py-1 text-slate-700 hover:bg-slate-50">
                        {e}
                      </button>
                    ))}
                  </div>
                )}
                <form onSubmit={onSubmit} className="flex items-end gap-2">
                  <label htmlFor="say" className="sr-only">
                    Your message
                  </label>
                  <input
                    id="say"
                    value={text}
                    disabled={busy}
                    onChange={(e) => setText(e.target.value)}
                    maxLength={500}
                    autoComplete="off"
                    placeholder={voice ? 'Speak with the mic, or type…' : 'Type your message…'}
                    className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-600 focus:ring-0"
                  />
                  <Mic enabled={voice} disabled={busy} onAudio={(b) => voiceTurn.mutate(b)} />
                  <Button type="submit" loading={say.isPending} disabled={!text.trim()}>
                    Send
                  </Button>
                </form>
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function Mic({ enabled, disabled, onAudio }: { enabled: boolean; disabled: boolean; onAudio: (b: Blob) => void }) {
  const [recording, setRecording] = useState(false);
  const rec = useRef<MediaRecorder | null>(null);
  const toggle = async () => {
    if (recording) return rec.current?.stop();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const r = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      r.ondataavailable = (e) => chunks.push(e.data);
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        onAudio(new Blob(chunks, { type: r.mimeType || 'audio/webm' }));
      };
      rec.current = r;
      r.start();
      setRecording(true);
      setTimeout(() => r.state === 'recording' && r.stop(), 20_000);
    } catch {
      setRecording(false);
    }
  };
  const label = !enabled ? 'Voice needs the Sarvam API and is off in the demo' : recording ? 'Stop and send' : 'Speak';
  return (
    <button
      type="button"
      onClick={toggle}
      disabled={!enabled || disabled}
      title={label}
      aria-label={label}
      aria-pressed={recording}
      className={cx('flex h-10 w-10 items-center justify-center rounded-full border text-lg disabled:cursor-not-allowed disabled:opacity-40', recording ? 'animate-pulse border-rose-400 bg-rose-50' : 'border-slate-300 bg-white hover:bg-slate-50')}
    >
      <span aria-hidden="true">🎙️</span>
    </button>
  );
}
