import { useEffect, useState } from 'react';

export type BackendStatus = 'checking' | 'waking' | 'ready' | 'down';

/**
 * Pings the API's /healthz once when the app loads.
 * The backend runs on Render's free tier, which sleeps after ~15 idle minutes and takes up to a
 * minute to wake. A warm server answers well within `wakingAfterMs`; anything slower is almost
 * certainly a cold start, so the UI can say so instead of looking frozen.
 * Never throws: a network error, a non-2xx answer or the give-up timeout all mean 'down'.
 */
export function useBackendStatus(url: string, wakingAfterMs = 1500, giveUpAfterMs = 90_000) {
  const [status, setStatus] = useState<BackendStatus>('checking');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    let done = false;
    const started = Date.now();
    const controller = new AbortController();
    const waking = setTimeout(() => {
      if (!done) setStatus('waking');
    }, wakingAfterMs);
    const tick = setInterval(() => setElapsedSeconds(Math.round((Date.now() - started) / 1000)), 1000);
    const giveUp = setTimeout(() => controller.abort(), giveUpAfterMs);
    const stop = () => {
      done = true;
      clearTimeout(waking);
      clearTimeout(giveUp);
      clearInterval(tick);
    };
    const finish = (next: BackendStatus) => {
      if (done) return;
      stop();
      setStatus(next);
    };

    fetch(url, { cache: 'no-store', signal: controller.signal })
      .then((res) => finish(res.ok ? 'ready' : 'down'))
      .catch(() => finish('down'));

    return () => {
      stop();
      controller.abort();
    };
  }, [url, wakingAfterMs, giveUpAfterMs]);

  return { status, elapsedSeconds };
}
