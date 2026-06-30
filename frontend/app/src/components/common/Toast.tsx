import { createContext, useCallback, useContext, useState } from "react";
import s from "./common.module.css";

interface Toast { id: number; message: string; kind: "info" | "error" }
interface ToastCtx { push: (message: string, kind?: "info" | "error") => void }

const Ctx = createContext<ToastCtx>({ push: () => {} });
export const useToast = () => useContext(Ctx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((message: string, kind: "info" | "error" = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, message, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  return (
    <Ctx.Provider value={{ push }}>
      {children}
      <div className={s.toastWrap} aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`${s.toast} ${t.kind === "error" ? s.toastErr : ""}`}>{t.message}</div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
