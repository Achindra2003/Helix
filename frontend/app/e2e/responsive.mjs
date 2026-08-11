// Responsive regression check: does any surface push content off the right edge,
// and does any control fall under the 24×24 hit-area floor (WCAG 2.2 SC 2.5.8)?
//
// Both failures are invisible to code review. A pane that clips rather than
// scrolls will hide a control while still reporting it as laid out, and a glyph
// button measures fine on screen until you check its box. Each was a real defect
// here: the topbar's controls sat past the right edge below ~700px, and four
// icon buttons were between 15×15 and 25×19.
//
// Boots its own backend (throwaway SQLite, stub provider) and Vite, drives the
// golden path far enough to have a real thread on screen, then walks the widths.
//
// Run from frontend/app:  node e2e/responsive.mjs
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { chromium } from "playwright";

const repo = resolve(import.meta.dirname, "..", "..", "..");
const API = "http://127.0.0.1:8000";
// localhost, not 127.0.0.1: vite binds ::1 on Windows, and the backend's CORS
// allowlist names http://localhost:5173 as the one permitted origin.
const UI = "http://localhost:5173";
const dbFile = join(tmpdir(), `helix-responsive-${Date.now()}.db`);
const children = [];

// The floor the project commits to (DESIGN.md, the .icon-act utility): WCAG 2.2
// SC 2.5.8, 24×24 — applied with the criterion's exceptions, see probe() below.
const TARGET_MIN = 24;

function boot(cmd, args, opts) {
  const child = spawn(cmd, args, { stdio: "ignore", ...opts });
  children.push(child);
  return child;
}

// Windows: killing a shell doesn't kill its children (vite outlives npm).
// taskkill /T takes the whole tree down. Resolves only once taskkill has
// actually exited — exiting the process before then leaves vite holding 5173,
// and the next run boots against a stale frontend.
function killTree(pid) {
  return new Promise((done) => {
    try {
      spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore" })
        .on("close", done).on("error", done);
    } catch { done(); }
  });
}

async function waitFor(url, label, tries = 120) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url);
      if (r.ok) return;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`${label} never came up at ${url}`);
}

// Runs in the page. Reports overflow past the document edge, and targets that
// fail WCAG 2.2 SC 2.5.8 — which is not simply "smaller than 24×24".
//
// The criterion has exceptions, and two of them apply throughout this UI:
//
//  · Spacing. An undersized target passes if a 24px-diameter circle centred on
//    its bounding box does not intersect another target, or another undersized
//    target's circle. Most of Helix's chip-shaped buttons are ~60×18 and sit in
//    well-spaced rows, so they pass on spacing rather than on size. Asserting a
//    flat 24×24 would report all of them and push the design toward padding it
//    does not need.
//  · User agent control. A native checkbox is 13×13 because the browser says
//    so. `accent-color` does not change its size, so authorship is untouched
//    and the exception holds.
//
// What is left after those is a genuine failure: a small target crowded against
// a neighbour, where the pointer cannot reliably separate the two.
function probe(min) {
  const docW = document.documentElement.clientWidth;
  const name = (e) => {
    const cls = (e.className || "").toString().split(" ")[0];
    return `${e.tagName.toLowerCase()}${cls ? "." + cls : ""}`;
  };
  const label = (e) =>
    (e.textContent || e.getAttribute("aria-label") || e.getAttribute("title") || e.tagName).trim().slice(0, 22);

  const targets = [...document.querySelectorAll("button, a, input, select, [role=button]")]
    .map((e) => ({ e, r: e.getBoundingClientRect() }))
    .filter(({ r }) => r.width > 0 && r.height > 0);

  // Native checkbox/radio: sized by the user agent, so exempt.
  const authored = targets.filter(({ e }) =>
    !(e.tagName === "INPUT" && (e.type === "checkbox" || e.type === "radio")));

  const centre = (r) => ({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
  const undersized = authored.filter(({ r }) => r.width < min || r.height < min);

  const failing = undersized.filter((t) => {
    const c = centre(t.r);
    for (const other of authored) {
      if (other.e === t.e) continue;
      const o = other.r;
      const isUnder = o.width < min || o.height < min;
      if (isUnder) {
        // circle-to-circle: centres must be at least one diameter apart
        const oc = centre(o);
        if (Math.hypot(c.x - oc.x, c.y - oc.y) < min) return true;
      } else {
        // circle-to-box: nearest point on the other target's box within radius
        const nx = Math.max(o.left, Math.min(c.x, o.right));
        const ny = Math.max(o.top, Math.min(c.y, o.bottom));
        if (Math.hypot(c.x - nx, c.y - ny) < min / 2) return true;
      }
    }
    return false;
  });

  return {
    scrollW: document.documentElement.scrollWidth,
    clientW: docW,
    offenders: [...document.querySelectorAll("*")]
      .filter((e) => e.getBoundingClientRect().right > docW + 1)
      .slice(0, 8)
      .map((e) => `${name(e)} → ${Math.round(e.getBoundingClientRect().right)}px`),
    tooSmall: failing.slice(0, 10)
      .map(({ e, r }) => `${label(e)} ${Math.round(r.width)}×${Math.round(r.height)}`),
    spaced: undersized.length - failing.length,
  };
}

const failures = [];

async function check(page, label, width) {
  await page.setViewportSize({ width, height: 860 });
  await page.waitForTimeout(500);
  const r = await page.evaluate(probe, TARGET_MIN);
  const overflow = r.scrollW - r.clientW;
  const ok = overflow <= 0 && r.tooSmall.length === 0;
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label} @ ${width}px` +
    `${overflow > 0 ? `  overflow +${overflow}px` : ""}` +
    `${r.spaced ? `  (${r.spaced} undersized but adequately spaced)` : ""}`);
  if (overflow > 0) {
    failures.push(`${label} @ ${width}px overflows by ${overflow}px: ${r.offenders.join(" | ")}`);
  }
  if (r.tooSmall.length) {
    failures.push(`${label} @ ${width}px fails SC 2.5.8 (under ${TARGET_MIN}px and crowded): ${r.tooSmall.join(" | ")}`);
  }
}

// A previous aborted run can leave vite holding 5173 (killing the npm shell
// does not always take its child down). Booting on top of that would test a
// stale frontend against a fresh database and fail somewhere confusing, so
// refuse up front instead.
async function assertPortsFree() {
  for (const [url, label] of [[`${API}/health`, "backend :8000"], [UI, "frontend :5173"]]) {
    try {
      await fetch(url, { signal: AbortSignal.timeout(1500) });
    } catch {
      continue; // nothing there, which is what we want
    }
    throw new Error(`${label} is already running. Stop it first — this script boots its own.`);
  }
}

async function main() {
  await assertPortsFree();
  boot(join(repo, "backend", ".venv", "Scripts", "python.exe"),
    ["-m", "uvicorn", "api.main:app", "--port", "8000"],
    // HELIX_DEV skips the JWT_SECRET guard; stub provider so no key is needed.
    { cwd: join(repo, "backend"), env: { ...process.env, LLM_PROVIDER: "stub", HELIX_DEV: "1", DATABASE_URL: `sqlite+aiosqlite:///${dbFile.replace(/\\/g, "/")}` } });
  boot("npm", ["run", "dev"], { cwd: join(repo, "frontend", "app"), shell: true });
  await waitFor(`${API}/health`, "backend");
  await waitFor(UI, "frontend");

  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.setDefaultTimeout(30_000);

  // A console error is a regression too, and this walk visits every route.
  const noise = new Set();
  page.on("console", (m) => { if (m.type() === "error") noise.add(m.text().slice(0, 160)); });
  page.on("pageerror", (e) => noise.add(`pageerror: ${e.message.slice(0, 160)}`));

  await page.goto(`${UI}/auth`);
  await page.getByRole("tab", { name: "Create account" }).click();
  await page.locator('input[type="email"]').fill("responsive@helix.team");
  await page.locator('input[type="password"]').fill("demo-password-1");
  await page.getByRole("button", { name: /Create account ⟶/ }).click();
  // /health answers as soon as the server binds; the first real request sits
  // behind lazy init and can outlast the default timeout on a cold machine.
  await page.waitForURL(/\/workspaces/, { timeout: 120_000 });
  await page.getByRole("button", { name: "+ New workspace" }).click();
  await page.getByPlaceholder(/Workspace name/).fill("responsive-check");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByRole("button", { name: /responsive-check/ }).first().click().catch(() => {});
  await page.getByRole("button", { name: "Begin a conversation" }).click();
  await page.getByPlaceholder(/Title \(e\.g\./).fill("Chunking strategy");
  await page.getByRole("button", { name: "Create", exact: true }).click();

  // A thread with a real reply in it — an empty stage hides most of the layout.
  const composer = page.getByPlaceholder(/Continue the thread/);
  await composer.fill("How should we chunk documents to improve recall?");
  await composer.press("Enter");
  await page.waitForFunction((sel) => !document.querySelector(sel)?.disabled,
    'button[title="Send (Enter)"]', { timeout: 60_000 });

  const wid = page.url().split("/w/")[1].split("/")[0];

  // Chat carries the most breakpoints: drawers at 1100, topbar wrap at 760.
  console.log("\nchat");
  for (const w of [1440, 1280, 1100, 1024, 900, 760, 560, 390]) await check(page, "chat", w);

  console.log("\nlanding");
  for (const w of [1440, 900, 560, 390]) {
    await page.goto(UI + "/");
    await page.waitForTimeout(400);
    await check(page, "landing", w);
  }

  for (const [label, path] of [["docs", "docs"], ["team", "members"], ["library", "library"]]) {
    console.log(`\n${label}`);
    for (const w of [760, 390]) {
      await page.goto(`${UI}/w/${wid}/${path}`);
      await page.waitForTimeout(400);
      await check(page, label, w);
    }
  }

  if (noise.size) {
    for (const n of noise) failures.push(`console error: ${n}`);
  }
}

let browser;
let code = 0;
try {
  await main();
  if (failures.length) {
    console.error(`\n${failures.length} regression(s):`);
    for (const f of failures) console.error("  · " + f);
    code = 1;
  } else {
    console.log("\nNo horizontal overflow, no target under 24×24, no console errors.");
  }
} catch (e) {
  console.error("FAILED:", e.message);
  code = 1;
}
// Close the browser here rather than at the end of main(): on the failure
// path main() never reaches its last line, and an open Playwright browser
// keeps the event loop alive indefinitely.
await browser?.close().catch(() => {});
await Promise.all(children.map((c) => killTree(c.pid)));
process.exit(code);
