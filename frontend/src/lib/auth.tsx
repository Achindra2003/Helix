import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { api, setToken, type User } from "./api";

const TOKEN_KEY = "helix_token";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // On boot: restore a saved token and validate it via /me.
  useEffect(() => {
    const saved = localStorage.getItem(TOKEN_KEY);
    if (!saved) {
      setLoading(false);
      return;
    }
    setToken(saved);
    api
      .me()
      .then(setUser)
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const apply = useCallback((token: string, u: User) => {
    localStorage.setItem(TOKEN_KEY, token);
    setToken(token);
    setUser(u);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const { token, user: u } = await api.login(email, password);
      apply(token, u);
    },
    [apply]
  );

  const register = useCallback(
    async (email: string, password: string) => {
      const { token, user: u } = await api.register(email, password);
      apply(token, u);
    },
    [apply]
  );

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
