import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { WakeBanner } from './WakeBanner';

afterEach(() => vi.unstubAllGlobals());

describe('WakeBanner', () => {
  it('explains a slow (cold-start) backend, then disappears once it answers', async () => {
    let answer: (res: Response) => void = () => {};
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => (answer = resolve))));

    render(<WakeBanner url="http://api.test/healthz" wakingAfterMs={10} />);
    expect(await screen.findByRole('status')).toHaveTextContent(/waking up the server/i);

    answer(new Response('{"status":"ok"}', { status: 200 }));
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
  });
});
