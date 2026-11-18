import { API_URL } from '../lib/api';
import { useBackendStatus } from '../lib/useBackendStatus';

type Props = {
  url?: string;
  wakingAfterMs?: number;
  wakingText?: (seconds: number) => string;
  downText?: string;
};

const defaultWaking = (s: number) =>
  `Waking up the server… Free-tier hosting sleeps when idle, so the first load can take up to a minute (${s} s).`;

/** Shows a small banner only while the backend is cold-starting, or if it never answers. */
export function WakeBanner({
  url = `${API_URL}/healthz`,
  wakingAfterMs,
  wakingText = defaultWaking,
  downText = 'The server is not responding right now. Please try again in a minute.',
}: Props) {
  const { status, elapsedSeconds } = useBackendStatus(url, wakingAfterMs);
  if (status !== 'waking' && status !== 'down') return null;

  const tone = status === 'waking' ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-rose-200 bg-rose-50 text-rose-900';
  return (
    <div
      role="status"
      aria-live="polite"
      className={`fixed inset-x-0 bottom-0 z-50 border-t px-4 py-2 text-center text-sm shadow-md ${tone}`}
    >
      {status === 'waking' ? wakingText(elapsedSeconds) : downText}
    </div>
  );
}
