// The half of Helix that isn't branching, seen through a browser.
//
// smoke.mjs drives the golden path; onboarding.mjs drives the ways in. Neither
// touches convergence — intent, verdicts, conclusions, notes, the ledger —
// which is the part of the product that actually distinguishes it, and which
// therefore has the most to lose from the failure this project keeps hitting:
// a capability that works on the server with no way to reach it in the UI.
//
// Two claims are asserted here, and they are the two that were broken:
//
//   1. A brand-new account's first screen shows convergence, not just a fork.
//      The seed used to stop at divergence.
//   2. The decisions ledger is reachable from where the question occurs. It
//      had no URL at all — it was component state behind a mode toggle — so
//      nothing anywhere could link to it.
//
// Runs on 8002/5175 so a dev pair and an onboarding run are both undisturbed.
// No LLM key: every assertion is about seeded content and navigation.
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { chromium } from "playwright";

const repo = resolve(import.meta.dirname, "..", "..", "..");
const API = "http://127.0.0.1:8002";
const UI = "http://localhost:5175";
const dbFile = join(tmpdir(), `helix-convergence-${Date.now()}.db`);
const children = [];
const failures = [];

function boot(cmd, args, opts) {
  const child = spawn(cmd, args, { stdio: "ignore", ...opts });
  children.push(child);
  return child;
}

// Windows: killing a shell doesn't kill its children (vite outlives npm).
function killTree(pid) {
  return new Promise((done) => {
    try {
      spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore" })
        .on("close", done).on("error", done);
    } catch { done(); }
  });
}

async function waitFor(url, label, tries = 160) {
  for (let i = 0; i < tries; i++) {
    try { if ((await fetch(url)).ok) return; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`${label} never came up at ${url}`);
}

async function assertPortsFree() {
  for (const [url, label] of [[`${API}/health`, "backend :8002"], [UI, "frontend :5175"]]) {
    try {
      await fetch(url, { signal: AbortSignal.timeout(1500) });
    } catch { continue; }
    throw new Error(`${label} is already running. Stop it first — this script boots its own.`);
  }
}

function check(ok, label) {
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}`);
  if (!ok) failures.push(label);
}

const text = (page) => page.evaluate(() => document.body.innerText);

let browser;
async function main() {
  await assertPortsFree();
  boot(join(repo, "backend", ".venv", "Scripts", "python.exe"),
    ["-m", "uvicorn", "api.main:app", "--port", "8002"],
    { cwd: join(repo, "backend"), env: {
      ...process.env, LLM_PROVIDER: "stub", HELIX_DEV: "1", FRONTEND_BASE_URL: UI,
      // The point of the run: the seeded workspace must be on.
      SEED_EXAMPLE_WORKSPACE: "1",
      DATABASE_URL: `sqlite+aiosqlite:///${dbFile.replace(/\\/g, "/")}`,
    } });
  boot("npx", ["vite", "--port", "5175", "--strictPort"],
    { cwd: join(repo, "frontend", "app"), shell: true, env: { ...process.env, VITE_API_BASE: API } });
  await waitFor(`${API}/health`, "backend");
  await waitFor(UI, "frontend");

  browser = await chromium.launch();
  const errors = new Set();
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  page.setDefaultTimeout(30_000);
  page.on("pageerror", (e) => errors.add(e.message.slice(0, 140)));

  // --- a brand-new account, which is the whole point ------------------------
  await page.goto(`${UI}/auth`);
  await page.getByRole("tab", { name: "Create account" }).click();
  await page.locator('input[type="email"]').fill("newcomer@helix.team");
  await page.locator('input[type="password"]').fill("demo-password-1");
  await page.getByRole("button", { name: /Create account ⟶/ }).click();
  await page.waitForURL(/\/workspaces|\/w\//, { timeout: 120_000 });

  console.log("\nthe first screen");
  if (/\/workspaces/.test(page.url())) {
    await page.getByText("Example workspace", { exact: true }).first().click();
  }
  await page.waitForURL(/\/w\//, { timeout: 30_000 });
  const wid = page.url().split("/w/")[1].split(/[/?]/)[0];

  // Conversation and branch rows are clickable divs, not buttons — so these
  // are text selectors rather than role ones.
  await page.getByText("Choosing a database", { exact: true }).first().click();
  await page.waitForTimeout(1200);
  const thread = await text(page);
  // Case-insensitive: the label is uppercased by CSS, and innerText reports
  // what is rendered rather than what is in the DOM.
  check(/concluded/i.test(thread), "the seeded thread shows what it concluded");
  check(/512 MB deployment target/.test(thread), "and the conclusion says why, not just that");
  // A note is human-to-human. Its presence in the transcript is the only way a
  // first-time reader learns the feature exists.
  check(/sounds like laziness/.test(thread), "a teammate note is rendered in the thread");

  // --- the door: the label that names a decision leads to all of them -------
  console.log("\nthe way into the ledger");
  await page.getByRole("button", { name: "Concluded", exact: true }).click();
  await page.waitForTimeout(1200);
  check(/view=decisions/.test(page.url()), "clicking Concluded opens the ledger");

  const ledger = await text(page);
  check(/512 MB deployment target/.test(ledger), "the conclusion is in the ledger");
  check(/installed far more often than it is scaled/.test(ledger),
    "and so is the abandoned fork's reason");
  check(/was trying: Price the Postgres-first path/.test(ledger),
    "the ledger shows what the abandoned branch was for");

  // --- the URL is real, not a click-only state ------------------------------
  // This is the defect underneath the discoverability one: the mode lived in
  // component state, so no link, bookmark, or teammate's paste could reach it.
  const fresh = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await fresh.goto(`${UI}/auth`);
  await fresh.getByRole("tab", { name: "Sign in" }).click();
  await fresh.locator('input[type="email"]').fill("newcomer@helix.team");
  await fresh.locator('input[type="password"]').fill("demo-password-1");
  await fresh.getByRole("button", { name: /Enter workspace ⟶/ }).click();
  await fresh.waitForURL(/\/workspaces|\/w\//, { timeout: 120_000 });
  await fresh.goto(`${UI}/w/${wid}/map?view=decisions`);
  await fresh.waitForTimeout(1500);
  check(/512 MB deployment target/.test(await text(fresh)),
    "the ledger opens directly from its own URL");

  // --- the verdict on the branch you are reading ----------------------------
  console.log("\nthe verdict in place");
  await page.goto(`${UI}/w/${wid}`);
  // Conversation and branch rows are clickable divs, not buttons — so these
  // are text selectors rather than role ones.
  await page.getByText("Choosing a database", { exact: true }).first().click();
  await page.waitForTimeout(1000);
  await page.getByText("What if we assume Postgres?", { exact: true }).first().click();
  await page.waitForTimeout(1200);
  const fork = await text(page);
  check(/Abandoned/.test(fork), "the fork carries its verdict where it is read");
  check(/installed far more often than it is scaled/.test(fork), "with the reason attached");

  await page.getByRole("button", { name: "Abandoned", exact: true }).click();
  await page.waitForTimeout(1000);
  check(/view=decisions/.test(page.url()), "and the verdict is a door to the ledger too");

  await browser.close();
  for (const e of errors) failures.push(`page error: ${e}`);
}

let code = 0;
try {
  await main();
  if (failures.length) {
    console.error(`\n${failures.length} failure(s):`);
    for (const f of failures) console.error("  · " + f);
    code = 1;
  } else {
    console.log("\nConvergence is visible on the first screen, and reachable.");
  }
} catch (e) {
  console.error("FAILED:", e.message);
  code = 1;
}
await browser?.close().catch(() => {});
await Promise.all(children.map((c) => killTree(c.pid)));
process.exit(code);
