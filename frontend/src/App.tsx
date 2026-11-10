import { useCallback, useEffect, useMemo, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError, setToken, setUnauthorizedHandler } from './lib/api';
import { AuthContext, loadUser, saveUser } from './lib/auth';
import type { Session, User } from './lib/types';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { TalkPage } from './pages/TalkPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (n, e) => !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 2,
      refetchOnWindowFocus: false,
    },
  },
});

export function Providers({ children, initialUser = null }: { children: React.ReactNode; initialUser?: User | null }) {
  const [user, setUser] = useState<User | null>(initialUser);
  const signIn = useCallback((s: Session) => {
    setToken(s.token);
    saveUser(s.user);
    setUser(s.user);
  }, []);
  const signOut = useCallback(() => {
    setToken(null);
    saveUser(null);
    setUser(null);
    queryClient.clear();
  }, []);
  useEffect(() => setUnauthorizedHandler(signOut), [signOut]);
  const auth = useMemo(() => ({ user, signIn, signOut }), [user, signIn, signOut]);
  return (
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>
    </QueryClientProvider>
  );
}

export default function App() {
  return (
    <Providers initialUser={loadUser()}>
      <BrowserRouter>
        <AuthContext.Consumer>
          {({ user }) => (
            <Routes>
              <Route path="/talk/:slug" element={<TalkPage />} />
              <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
              <Route path="/" element={user ? <DashboardPage /> : <Navigate to="/login" replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          )}
        </AuthContext.Consumer>
      </BrowserRouter>
    </Providers>
  );
}
