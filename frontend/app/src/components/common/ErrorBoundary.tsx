// What a stranger sees when the app breaks.
//
// There was no boundary anywhere, so a single render error unmounted the whole
// tree and left a white page: no message, no way back, nothing to report. To
// the person it happens to that is not "a bug", that is "this product does not
// work" — and they have no way to tell you which screen did it.
//
// A boundary only catches errors thrown while rendering, in lifecycle methods
// and in constructors below it. Event handlers and async work are *not*
// caught by design, which is fine here: those paths already route their
// failures through the toast, and this exists for the case nothing else can
// see.
//
// Two ways out, because "Reload" alone is a trap — if the route itself is what
// throws, reloading returns to the same broken screen forever. Going home
// resets the route as well as the tree.
import React from "react";
import { Logo } from "@/components/brand/Logo";
import s from "./common.module.css";

interface Props {
  children: React.ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // The console is the only reporter this app has — telemetry is
    // server-side, and inventing a client error endpoint here would be
    // building a feature nobody asked for. The component stack is the useful
    // half: it names the screen.
    console.error("Helix: render error", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className={s.boundary} role="alert">
        <div className={s.boundaryMark} aria-hidden><Logo size={64} /></div>
        <h1 className={s.boundaryTitle}>This page stopped short.</h1>
        <p className={s.boundaryBody}>
          Something failed while drawing this screen. Your work is not lost —
          conversations, branches and verdicts are saved on the server as they
          happen, not in this tab.
        </p>
        {/* Shown, not hidden: it is the only thing that makes a bug report
            useful, and on a self-hosted instance the person reading it is
            often the person running it. */}
        <pre className={s.boundaryDetail}>{error.message || String(error)}</pre>
        <div className={s.boundaryActs}>
          <button className={s.boundaryBtn} onClick={() => window.location.reload()}>
            Reload this page
          </button>
          <button
            className={`${s.boundaryBtn} ${s.boundaryBtnQuiet}`}
            onClick={() => window.location.assign("/")}
          >
            Back to the start
          </button>
        </div>
      </div>
    );
  }
}
