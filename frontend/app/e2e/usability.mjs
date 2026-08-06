// The things that work for us and break for strangers.
//
// smoke.mjs proves the golden path, convergence.mjs proves the record is
// readable and exportable. Neither notices the two failures a first-time,
// non-mouse or unlucky visitor hits first:
//
//   1. The app's primary navigation — the conversation list and the branch
//      tree — were clickable `div`s with no role, no tab stop and no key
//      handler. A keyboard-only user could not switch threads at all.
//   2. There was no error boundary anywhere, so one bad render unmounted the
//      whole tree and left a white page: no message, no way back, nothing to
//      report.
//
// Both are asserted here against the real app, because both are the kind of
// claim that is easy to believe and hard to keep.
//
// Runs on 8003/5176 so a dev pair, an onboarding run and a convergence run are
// all undisturbed. No LLM key: every assertion is seeded content or navigation.
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { chromium } from "playwright";

const repo = resolve(import.meta.dirname, "..", "..", "..");
const API = "http://127.0.0.1:8003";
const UI = "http://localhost:5176";
const dbFile = join(tmpdir(), `helix-usability-${Date.now()}.db`);
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
      if (process.platform === "win32") {
        spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore" })
          .on("close", done);
      } else {
        process.kill(-pid, "SIGKILL");
        done();
      }
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

function check(ok, label) {
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}`);
  if (!ok) failures.push(label);
}

const text = (page) => page.evaluate(() => document.body.innerText);

let browser;
async function main() {
  boot(join(repo, "backend", ".venv", "Scripts", "python.exe"),
    ["-m", "uvicorn", "api.main:app", "--port", "8003"],
    { cwd: join(repo, "backend"), env: {
      ...process.env, LLM_PROVIDER: "stub", HELIX_DEV: "1", FRONTEND_BASE_URL: UI,
      SEED_EXAMPLE_WORKSPACE: "1",
      DATABASE_URL: `sqlite+aiosqlite:///${dbFile.replace(/\\/g, "/")}`,
    } });
  boot("npx", ["vite", "--port", "5176", "--strictPort"],
    { cwd: join(repo, "frontend", "app"), shell: true, env: { ...process.env, VITE_API_BASE: API } });
  await waitFor(`${API}/health`, "backend");
  await waitFor(UI, "frontend");

  browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  page.setDefaultTimeout(30_000);

  // --- the landing page of an open-source product ---------------------------
  console.log("\nthe landing page points somewhere");
  await page.goto(UI);
  const repoLink = page.locator('a[href*="github.com"]').first();
  check(await repoLink.count() > 0, "the landing page links to the repository");

  // --- a keyboard-only user can navigate ------------------------------------
  console.log("\nnavigation without a mouse");
  await page.goto(`${UI}/auth`);
  await page.getByRole("tab", { name: "Create account" }).click();
  await page.locator('input[type="email"]').fill("keyboard@helix.team");
  await page.locator('input[type="password"]').fill("demo-password-1");
  await page.getByRole("button", { name: /Create account ⟶/ }).click();
  await page.waitForURL(/\/workspaces|\/w\//, { timeout: 120_000 });
  if (/\/workspaces/.test(page.url())) {
    // The picker already had this right — and it is how we get in here.
    await page.getByRole("button", { name: /Example workspace/ }).first().press("Enter");
  }
  await page.waitForURL(/\/w\//, { timeout: 30_000 });
  const wid = page.url().split("/w/")[1].split(/[/?]/)[0];
  await page.waitForTimeout(1500);

  // A conversation row is a button to assistive tech, and answers the keyboard.
  const convRow = page.getByRole("button", { name: /Deployment constraints/ }).first();
  check(await convRow.count() > 0, "conversation rows expose themselves as buttons");
  check(await convRow.getAttribute("tabindex") === "0", "and are reachable by Tab");
  await convRow.press("Enter");
  await page.waitForTimeout(1200);
  check(await convRow.getAttribute("aria-current") === "true",
    "pressing Enter on a conversation opens it");

  // Same for the branch tree, the other half of the primary navigation.
  await page.getByRole("button", { name: /Choosing a database/ }).first().press("Enter");
  await page.waitForTimeout(1200);
  const forkRow = page.getByRole("button", { name: /What if we assume Postgres/ }).first();
  check(await forkRow.count() > 0, "branch rows expose themselves as buttons");
  check(await forkRow.getAttribute("tabindex") === "0", "and are reachable by Tab");
  await forkRow.press("Enter");
  await page.waitForTimeout(1500);
  check(/Abandoned/.test(await text(page)), "pressing Enter on a branch opens it");

  // The reason the branch tree takes the role on its *name* and not on the
  // whole row: `role="button"` is children-presentational, so a row-level role
  // would prune the row's own controls from the accessibility tree. These have
  // to survive the fix that was supposed to help them.
  // Named, too: a button whose only content is a glyph takes that glyph as its
  // accessible name, so these announced as "⚖", "✎", "✕" until they were given
  // one.
  check(await page.getByRole("button", { name: /came of|verdict/i }).count() > 0,
    "and a branch's own actions are still reachable, and named");

  // Space activates too — the one people forget, and its default is to scroll.
  await page.getByRole("button", { name: /Deployment constraints/ }).first().press(" ");
  await page.waitForTimeout(1200);
  check(/three that matter/i.test(await text(page)), "Space activates a row as well");

  // --- what an unreachable server says --------------------------------------
  // The message used to ask "is the backend running on :8000?", which is
  // nonsense to anyone on a deployed instance — and it is the first thing
  // anyone sees when their connection drops.
  console.log("\nwhen the server cannot be reached");
  await page.route("**/conversations", (route) =>
    route.request().method() === "POST" ? route.abort() : route.continue());
  await page.getByTitle("New conversation").first().click();
  await page.getByPlaceholder(/^Title/).fill("will not reach");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.waitForTimeout(1200);
  const offline = await text(page);
  check(offline.includes(API), "the error names the address it actually called");
  check(!/running on :8000/.test(offline), "and not a port from someone's laptop");
  await page.unroute("**/conversations");

  // --- when a render fails --------------------------------------------------
  // Forced the way it actually happens in the wild: the server answers with a
  // shape the client did not expect, and something downstream throws while
  // rendering. Before the boundary this was a white page.
  console.log("\nwhen a render fails");
  await page.route("**/conversations?workspace_id=*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: "not a list" }),
    }));
  await page.goto(`${UI}/w/${wid}`);
  await page.waitForTimeout(2500);
  const broken = await text(page);
  check(broken.trim().length > 0, "a broken render is not a blank page");
  check(/stopped short/i.test(broken), "it says what happened");
  check(/not lost/i.test(broken), "and that the work is safe");
  check(await page.getByRole("button", { name: /Reload this page/ }).count() > 0,
    "with a way to retry");
  check(await page.getByRole("button", { name: /Back to the start/ }).count() > 0,
    "and a way out, since reloading a broken route just breaks again");

  await browser.close();
}

let code = 0;
try {
  await main();
  if (failures.length) {
    console.error(`\n${failures.length} failure(s):`);
    for (const f of failures) console.error("  · " + f);
    code = 1;
  } else {
    console.log("\nReachable without a mouse, and legible when it breaks.");
  }
} catch (e) {
  console.error("FAILED:", e.message);
  code = 1;
}
await browser?.close().catch(() => {});
await Promise.all(children.map((c) => killTree(c.pid)));
process.exit(code);
