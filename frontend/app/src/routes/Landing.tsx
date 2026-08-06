import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  motion,
  useReducedMotion,
  useScroll,
  useTransform,
  useInView,
  type Variants,
} from "framer-motion";
import { Logo } from "@/components/brand/Logo";
import { Frontispiece } from "@/components/brand/Frontispiece";
import { ThemeToggle } from "@/components/common/ThemeToggle";
import { useSession } from "@/store/session";
import s from "./landing.module.css";

const EASE = [0.22, 0.61, 0.21, 1] as const; // --ease-quill

/** A block that rises into place the first time it scrolls into view. */
function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: reduce ? 0 : 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.6, ease: EASE, delay }}
    >
      {children}
    </motion.div>
  );
}

/** Counts a number up when it first enters the viewport. */
function CountUp({ to, suffix = "" }: { to: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const reduce = useReducedMotion();
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!inView) return;
    if (reduce) { setN(to); return; }
    let raf = 0;
    const start = performance.now();
    const dur = 1100;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      setN(Math.round(eased * to));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, to, reduce]);
  return <span ref={ref}>{n}{suffix}</span>;
}

/* ── feature motifs — line-art in the Frontispiece vocabulary ─────── */
const stroke = { fill: "none", strokeLinecap: "round", strokeLinejoin: "round" } as const;

function MotifShared() {
  const authors = [
    [46, 40], [128, 34], [50, 130], [140, 138],
  ];
  return (
    <svg viewBox="0 0 190 170" width="72%" aria-hidden>
      <g {...stroke} stroke="var(--rule)" strokeWidth="1">
        {authors.map(([x, y], i) => (
          <line key={i} x1={x} y1={y} x2={95} y2={85} />
        ))}
      </g>
      {authors.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="6" fill="var(--gilt)" opacity="0.55" />
      ))}
      <circle cx="95" cy="85" r="26" fill="none" stroke="var(--gilt-1)" strokeWidth="1.2" strokeDasharray="90 12" strokeLinecap="round" />
      <g {...stroke} strokeWidth="1.6">
        <path d="M84 70 Q95 85 84 100" stroke="var(--ink)" opacity="0.8" />
        <path d="M106 70 Q95 85 106 100" stroke="var(--oxblood)" opacity="0.8" />
        <line x1="88" y1="78" x2="102" y2="78" stroke="var(--gilt-1)" />
        <line x1="88" y1="92" x2="102" y2="92" stroke="var(--gilt-1)" />
      </g>
    </svg>
  );
}

function MotifBranch() {
  return (
    <svg viewBox="0 0 200 150" width="76%" aria-hidden>
      <g {...stroke} strokeWidth="1.6">
        {/* main spine */}
        <path d="M20 46 H180" stroke="var(--ink)" opacity="0.75" />
        {/* branch derived from a node */}
        <path d="M74 46 C90 46 90 104 108 104 H180" stroke="var(--oxblood)" opacity="0.7" />
      </g>
      {[20, 47, 74, 101, 128].map((x) => (
        <circle key={x} cx={x} cy={46} r="5.5" fill="var(--paper-0)" stroke="var(--ink)" strokeWidth="1.4" />
      ))}
      {[108, 135, 162].map((x) => (
        <circle key={x} cx={x} cy={104} r="5.5" fill="var(--paper-0)" stroke="var(--oxblood)" strokeWidth="1.4" />
      ))}
      <circle cx="74" cy="46" r="8.5" fill="none" stroke="var(--gilt-1)" strokeWidth="1.1" strokeDasharray="3 3" />
    </svg>
  );
}

function MotifLoop() {
  const reduce = useReducedMotion();
  const R = 52, cx = 95, cy = 82;
  const nodes = [-90, 30, 150].map((deg) => {
    const a = (deg * Math.PI) / 180;
    return [cx + R * Math.cos(a), cy + R * Math.sin(a)];
  });
  const labels = ["reason", "reflect", "synth"];
  return (
    <svg viewBox="0 0 190 170" width="72%" aria-hidden>
      <motion.g
        style={{ transformOrigin: `${cx}px ${cy}px` }}
        animate={reduce ? undefined : { rotate: 360 }}
        transition={{ duration: 26, ease: "linear", repeat: Infinity }}
      >
        <circle cx={cx} cy={cy} r={R} fill="none" stroke="var(--gilt-1)" strokeWidth="1.2" strokeDasharray="120 10" strokeLinecap="round" />
        <path d={`M${cx + R - 4} ${cy - 8} l 8 8 l -9 4`} {...stroke} stroke="var(--gilt-1)" strokeWidth="1.4" fill="none" />
      </motion.g>
      {nodes.map(([x, y], i) => (
        <g key={i}>
          <circle cx={x} cy={y} r="15" fill="var(--paper-0)" stroke="var(--oxblood)" strokeWidth="1.3" />
          <text x={x} y={y + 3} textAnchor="middle" fontFamily="var(--font-mono)" fontSize="8" fill="var(--ink-2)">{labels[i]}</text>
        </g>
      ))}
      <text x={cx} y={cy + 3} textAnchor="middle" fontFamily="var(--font-display)" fontSize="11" fill="var(--gilt-1)">✓</text>
    </svg>
  );
}

function MotifMemory() {
  const faint = [[30, 30], [64, 118], [150, 40], [120, 128], [40, 88], [168, 100]];
  return (
    <svg viewBox="0 0 200 160" width="78%" aria-hidden>
      {faint.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="3" fill="var(--ink-faint)" opacity="0.4" />
      ))}
      <g {...stroke} stroke="var(--rule)" strokeWidth="1">
        <line x1="100" y1="80" x2="30" y2="30" />
        <line x1="100" y1="80" x2="150" y2="40" />
      </g>
      <circle cx="30" cy="30" r="5.5" fill="var(--gilt)" opacity="0.7" />
      <circle cx="150" cy="40" r="5.5" fill="var(--gilt)" opacity="0.7" />
      {/* resurfaced chip */}
      <g transform="translate(60 66)">
        <rect x="0" y="0" width="80" height="28" rx="14" fill="var(--paper-0)" stroke="var(--oxblood)" strokeWidth="1.2" />
        <text x="40" y="18" textAnchor="middle" fontFamily="var(--font-ui)" fontSize="9" fill="var(--oxblood)">✦ explored before</text>
      </g>
    </svg>
  );
}

function MotifAgent() {
  return (
    <svg viewBox="0 0 190 160" width="70%" aria-hidden>
      {/* gate posts */}
      <g {...stroke} stroke="var(--ink)" strokeWidth="1.6" opacity="0.7">
        <line x1="60" y1="34" x2="60" y2="126" />
        <line x1="130" y1="34" x2="130" y2="126" />
        <path d="M60 44 Q95 24 130 44" fill="none" />
      </g>
      {/* three tool tokens, one barred */}
      <circle cx="95" cy="66" r="13" fill="var(--paper-0)" stroke="var(--gilt-1)" strokeWidth="1.3" />
      <text x="95" y="70" textAnchor="middle" fontSize="12">⌕</text>
      <circle cx="95" cy="100" r="13" fill="var(--paper-0)" stroke="var(--gilt-1)" strokeWidth="1.3" />
      <text x="95" y="105" textAnchor="middle" fontSize="12">◫</text>
      {/* barred (not allowed) tool floating outside */}
      <g opacity="0.5">
        <circle cx="162" cy="80" r="12" fill="none" stroke="var(--ink-faint)" strokeWidth="1.2" strokeDasharray="3 3" />
        <line x1="154" y1="88" x2="170" y2="72" stroke="var(--oxblood)" strokeWidth="1.4" />
      </g>
      {/* approval seal */}
      <circle cx="30" cy="80" r="14" fill="none" stroke="var(--oxblood)" strokeWidth="1.4" />
      <text x="30" y="85" textAnchor="middle" fontSize="13" fill="var(--oxblood)">✓</text>
    </svg>
  );
}

function MotifLive() {
  const reduce = useReducedMotion();
  const dots = [
    { x: 55, y: 60, c: "var(--oxblood)" },
    { x: 120, y: 60, c: "var(--verde)" },
    { x: 150, y: 108, c: "var(--violet)" },
  ];
  return (
    <svg viewBox="0 0 200 150" width="76%" aria-hidden>
      <g {...stroke} strokeWidth="1.6">
        <path d="M24 60 H176" stroke="var(--ink)" opacity="0.6" />
        <path d="M90 60 C110 60 110 108 128 108 H176" stroke="var(--rule)" strokeWidth="1.4" />
      </g>
      {[24, 55, 90, 120].map((x) => (
        <circle key={x} cx={x} cy={60} r="4.5" fill="var(--paper-0)" stroke="var(--ink)" strokeWidth="1.2" />
      ))}
      {dots.map((d, i) => (
        <motion.circle
          key={i}
          cx={d.x} cy={d.y} r="7" fill={d.c}
          animate={reduce ? undefined : { opacity: [0.55, 1, 0.55], scale: [1, 1.14, 1] }}
          transition={{ duration: 2.4, repeat: Infinity, delay: i * 0.5, ease: "easeInOut" }}
          style={{ transformOrigin: `${d.x}px ${d.y}px` }}
        />
      ))}
    </svg>
  );
}

type Feature = {
  tag: string; title: string; body: string; art: React.ReactNode; id: string;
};
const FEATURES: Feature[] = [
  {
    id: "shared", tag: "Shared context", title: "One assistant. Every mind.",
    body: "Everyone writes into the same context. Open a teammate's thread and the assistant already knows what they explored — because context is assembled from shared history, never copied. A single brain your whole team reasons with.",
    art: <MotifShared />,
  },
  {
    id: "branch", tag: "Branching", title: "Fork a thought. Keep the root.",
    body: "Branch any message to chase a divergent path. Nothing is duplicated — a fork is one row, and history is derived by walking the ancestor spine. Two directions from one point, with no cross-contamination. Structural sharing, exactly like Git.",
    art: <MotifBranch />,
  },
  {
    id: "reason", tag: "Deep reasoning", title: "Watch it converge — then stop.",
    body: "Deep runs loop reason → reflect → synthesize and halt on genuine convergence, measured with embeddings rather than a fixed number of passes. Steer it mid-thought. Close the tab and reconnect to a run that never stopped executing.",
    art: <MotifLoop />,
  },
  {
    id: "memory", tag: "Memory", title: "It resurfaces what you forgot.",
    body: "As you type, Helix surfaces the threads you've already explored. Upload a document and answers cite it inline. One semantic substrate sits under search, recall, and grounding — the workspace remembers so you don't have to.",
    art: <MotifMemory />,
  },
  {
    id: "agents", tag: "Governed agents", title: "The tools it may use — and only those.",
    body: "Agent mode runs a governed tool loop: an owner-set allowlist, sensitive calls paused for human approval, and enforcement by binding. An un-allowed tool is a door the model never learns exists — nothing to jailbreak, because it was never offered.",
    art: <MotifAgent />,
  },
  {
    id: "live", tag: "Together", title: "A shared canvas, live.",
    body: "See who's on which branch in real time. Runs stream to everyone watching, presence rides the conversation map, and a teammate's finished thought lands in your bell. One workspace, many minds, one connection.",
    art: <MotifLive />,
  },
];

// Where the source lives. Kept here as one constant because two places on
// this page point at it, and a fork that retargets one and not the other is
// worse than a fork that retargets neither.
const REPO_URL = "https://github.com/Achindra2003/Helix";

export function Landing() {
  const nav = useNavigate();
  const user = useSession((s) => s.user);
  const pageRef = useRef<HTMLDivElement>(null);
  const heroRef = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);
  const reduce = useReducedMotion();

  const enterHref = user ? "/workspaces" : "/auth";
  const enter = () => nav(enterHref);

  // parallax the hero instrument as it scrolls away
  const { scrollYProgress } = useScroll({
    container: pageRef,
    target: heroRef,
    offset: ["start start", "end start"],
  });
  const artY = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : 120]);
  const artOpacity = useTransform(scrollYProgress, [0, 0.8], [1, 0.15]);

  const heroContainer: Variants = {
    hidden: {},
    show: { transition: { staggerChildren: 0.09, delayChildren: 0.05 } },
  };
  const heroItem: Variants = {
    hidden: { opacity: 0, y: reduce ? 0 : 20 },
    show: { opacity: 1, y: 0, transition: { duration: 0.65, ease: EASE } },
  };

  return (
    <div
      className={s.page}
      ref={pageRef}
      onScroll={(e) => setScrolled(e.currentTarget.scrollTop > 40)}
    >
      {/* masthead */}
      <nav className={`${s.nav} ${scrolled ? s.navSolid : ""}`}>
        <div className={s.navBrand}>
          <Logo size={30} />
          <span className={s.navName}>Helix</span>
        </div>
        <div className={s.navLinks}>
          <a className={`${s.navLink} ${s.navHideSm}`} href="#features">Features</a>
          <a className={`${s.navLink} ${s.navHideSm}`} href="#claim">The claim</a>
          {/* The landing page of an open-source product pointed at no
              repository. Every claim below — self-hostable, your keys, the
              test count — is checkable only if someone can get to the source,
              and this is the one page strangers actually arrive on. */}
          <a className={s.navLink} href={REPO_URL} target="_blank" rel="noreferrer">
            GitHub ↗
          </a>
          <ThemeToggle />
          <button className={s.ctaGhost} onClick={enter} style={{ padding: "9px 16px", fontSize: 13.5 }}>
            {user ? "Enter workspace ⟶" : "Sign in ⟶"}
          </button>
        </div>
      </nav>

      {/* hero */}
      <header className={s.hero} ref={heroRef}>
        <motion.div className={s.heroCopy} variants={heroContainer} initial="hidden" animate="show">
          <motion.div className={s.heroEyebrow} variants={heroItem}>
            A workspace for the recursive mind
          </motion.div>
          <motion.h1 className={s.heroTitle} variants={heroItem}>
            The AI workspace<br />that <em>remembers</em>.
          </motion.h1>
          <motion.p className={s.heroSub} variants={heroItem}>
            One shared context. Many branching minds. Reasoning you can watch
            converge — and steer, and stop.
          </motion.p>
          <motion.div className={s.heroCtas} variants={heroItem}>
            <motion.button
              className={s.cta}
              onClick={enter}
              whileHover={reduce ? undefined : { scale: 1.035, y: -1 }}
              whileTap={{ scale: 0.97 }}
              transition={{ type: "spring", stiffness: 400, damping: 22 }}
            >
              {user ? "Enter workspace" : "Enter Helix"} ⟶
            </motion.button>
            <a className={s.ctaGhost} href="#features">See how it thinks</a>
          </motion.div>
        </motion.div>

        <motion.div className={s.heroArt} style={{ y: artY, opacity: artOpacity }}>
          <Frontispiece size={520} />
        </motion.div>

        {!reduce && (
          <motion.div
            className={s.scrollCue}
            animate={{ y: [0, 7, 0], opacity: [0.4, 0.9, 0.4] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            aria-hidden
          >
            ⌄
          </motion.div>
        )}
      </header>

      {/* manifesto */}
      <section className={s.manifesto}>
        <Reveal>
          <p className={s.manifestoText}>
            Most AI chat is a solo transcript you throw away. Helix is a{" "}
            <b>shared mind</b> your whole team writes into — <b>branchable</b>,
            permanent, and <b>honest</b> about how it reasons.
          </p>
        </Reveal>
      </section>

      {/* features */}
      <section className={s.features} id="features">
        {FEATURES.map((f) => (
          <div className={s.feature} key={f.id} id={f.id}>
            <Reveal>
              <div>
                <div className={s.featureTag}>{f.tag}</div>
                <h2 className={s.featureTitle}>{f.title}</h2>
                <p className={s.featureBody}>{f.body}</p>
              </div>
            </Reveal>
            <div className={s.featureArt}>
              <Reveal delay={0.08}>
                <div className={s.artPlate}>{f.art}</div>
              </Reveal>
            </div>
          </div>
        ))}
      </section>

      {/* the measured claim */}
      <section className={s.claim} id="claim">
        <Reveal>
          <div className={s.claimEyebrow}>We measured it</div>
          <h2 className={s.claimTitle}>
            We don't claim a smarter model.<br />We claim one you can <em>see</em>.
          </h2>
        </Reveal>
        <div className={s.stats}>
          {[
            { num: <CountUp to={8} suffix="/8" />, label: "deep runs that converged on the hard question set" },
            { num: <CountUp to={48} suffix="%" />, label: "of blind 4-pass tokens — at higher quality" },
            { num: <CountUp to={374} />, label: "tests, run with no network and no API key" },
          ].map((st, i) => (
            <Reveal key={i} delay={i * 0.1}>
              <div className={s.stat}>
                <div className={s.statNum}>{st.num}</div>
                <div className={s.statLabel}>{st.label}</div>
              </div>
            </Reveal>
          ))}
        </div>
        <Reveal delay={0.15}>
          <p className={s.claimBody}>
            On a question set engineered so single-pass answers plausibly fail,
            adaptive reasoning matched blind four-pass iteration on quality at{" "}
            <b>less than half the tokens</b> — while a single good pass still edged
            both. So the honest pitch isn't higher IQ. It's{" "}
            <b>transparency, steerability, and cost</b>.
          </p>
        </Reveal>
      </section>

      {/* closing */}
      <footer className={s.close}>
        <Reveal>
          <h2 className={s.closeTitle}>Open the workspace.</h2>
          <motion.button
            className={s.cta}
            onClick={enter}
            whileHover={reduce ? undefined : { scale: 1.035, y: -1 }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: "spring", stiffness: 400, damping: 22 }}
          >
            {user ? "Enter workspace" : "Begin"} ⟶
          </motion.button>
          <div className={s.colophon}>
            <div className={s.colophonMark}><Logo size={28} /></div>
            <div className={s.colophonLine}>"One shared context — many branching minds."</div>
            <div>Helix — a specialisation project · FastAPI · React · a vendored Ouroboros engine</div>
            <div>
              Self-hostable. Your keys, your data.{" "}
              <a href={REPO_URL} target="_blank" rel="noreferrer">Source on GitHub</a> · MIT
            </div>
          </div>
        </Reveal>
      </footer>
    </div>
  );
}
