// The ways a person gets INTO Helix, and back in when they're locked out.
//
// smoke.mjs drives the golden path of someone already inside a workspace. It
// covered none of this, and three separate features shipped with one half
// missing and stayed broken for weeks as a result: the invite link had no
// frontend route, password reset had no frontend at all, and the picker's join
// field rejected the very link the app handed out. Each was found by accident.
//
// So this is the other half of the product's surface: invite → join → role,
// and forgotten → reset → sign in. It asserts and exits non-zero, because a
// check that only prints is a check nobody reads.
//
// Runs on 8001/5174 so a dev pair on 8000/5173 is never disturbed.
import { spawn, spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { chromium } from "playwright";

const repo = resolve(import.meta.dirname, "..", "..", "..");
const API = "http://127.0.0.1:8001";
const UI = "http://localhost:5174";
const dbFile = join(tmpdir(), `helix-onboarding-${Date.now()}.db`);
const children = [];
const failures = [];

function boot(cmd, args, opts) {
  const child = spawn(cmd, args, { stdio: "ignore", ...opts });
  children.push(child);
  return child;
}

// Windows: killing a shell doesn't kill its children (vite outlives npm).
// Resolves only once taskkill has exited — exiting first leaves vite holding
// the port and the next run boots against a stale frontend.
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

// A previous aborted run can leave vite holding the port; booting on top of it
// would test a stale frontend against a fresh database.
async function assertPortsFree() {
  for (const [url, label] of [[`${API}/health`, "backend :8001"], [UI, "frontend :5174"]]) {
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

async function signUp(page, email) {
  await page.goto(`${UI}/auth`);
  await page.getByRole("tab", { name: "Create account" }).click();
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill("demo-password-1");
  await page.getByRole("button", { name: /Create account ⟶/ }).click();
  // /health answers as soon as the server binds; the first real request sits
  // behind lazy init and can outlast the default timeout on a cold machine.
  await page.waitForURL(/\/workspaces|\/w\//, { timeout: 120_000 });
}

/** An invite URL for `wid`, minted through the API as the owner would. */
async function inviteUrl(page, wid, role) {
  return page.evaluate(async ([api, wid, role]) => {
    const t = localStorage.getItem("helix.token");
    const r = await fetch(`${api}/api/workspaces/${wid}/invites`, {
      method: "POST",
      headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    return (await r.json()).url;
  }, [API, wid, role]);
}

const local = (url) => url.replace(/^https?:\/\/[^/]+/, UI);

let browser;
async function main() {
  await assertPortsFree();
  boot(join(repo, "backend", ".venv", "Scripts", "python.exe"),
    ["-m", "uvicorn", "api.main:app", "--port", "8001"],
    { cwd: join(repo, "backend"), env: {
      ...process.env, LLM_PROVIDER: "stub", HELIX_DEV: "1", FRONTEND_BASE_URL: UI,
      DATABASE_URL: `sqlite+aiosqlite:///${dbFile.replace(/\\/g, "/")}`,
    } });
  boot("npx", ["vite", "--port", "5174", "--strictPort"],
    { cwd: join(repo, "frontend", "app"), shell: true, env: { ...process.env, VITE_API_BASE: API } });
  await waitFor(`${API}/health`, "backend");
  await waitFor(UI, "frontend");

  browser = await chromium.launch();
  const errors = new Set();
  const owner = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  owner.setDefaultTimeout(30_000);
  owner.on("pageerror", (e) => errors.add(e.message.slice(0, 140)));

  await signUp(owner, "ada@helix.team");
  await owner.getByRole("button", { name: "+ New workspace" }).click();
  await owner.getByPlaceholder(/Workspace name/).fill("rag-quality");
  await owner.getByRole("button", { name: "Create", exact: true }).click();
  await owner.getByRole("button", { name: /rag-quality/ }).first().click().catch(() => {});
  const wid = owner.url().split("/w/")[1].split("/")[0];

  // --- the owner is handed a LINK, not a token -----------------------------
  console.log("\ninvite");
  await owner.goto(`${UI}/w/${wid}/members`);
  await owner.waitForTimeout(1000);
  await owner.locator('select[title*="invited person"]').selectOption("observer");
  await owner.getByRole("button", { name: "+ Invite" }).click();
  await owner.waitForTimeout(800);
  const dialog = await owner.evaluate(() => document.body.innerText);
  const shown = (dialog.match(/https?:\/\/\S*\/invite\/\S+/) || [])[0] ?? "";
  check(!!shown, "the invite dialog shows a join link");
  check(/joins as observer/i.test(dialog), "and states the role the link grants");
  await owner.keyboard.press("Escape");

  // --- a signed-in stranger follows it -------------------------------------
  const mate = await (await browser.newContext({ viewport: { width: 1280, height: 860 } })).newPage();
  mate.on("pageerror", (e) => errors.add(e.message.slice(0, 140)));
  await signUp(mate, "grace@helix.team");
  await mate.goto(local(shown));
  await mate.waitForURL(/\/w\//, { timeout: 60_000 }).catch(() => {});
  check(mate.url().includes(`/w/${wid}`), "following the link lands inside the workspace");
  await mate.waitForTimeout(1500);
  const mateSees = await mate.evaluate(() => document.body.innerText);
  check(/Observer/.test(mateSees), "and with the role the invite granted, not a default");

  // --- a signed-OUT stranger follows one ------------------------------------
  const cold = await (await browser.newContext({ viewport: { width: 1280, height: 860 } })).newPage();
  cold.on("pageerror", (e) => errors.add(e.message.slice(0, 140)));
  const second = await inviteUrl(owner, wid, "collaborator");
  await cold.goto(local(second));
  await cold.waitForURL(/\/auth/, { timeout: 30_000 }).catch(() => {});
  check(/\/auth/.test(cold.url()), "signed out, an invite sends you to sign in");
  await cold.getByRole("tab", { name: "Create account" }).click();
  await cold.locator('input[type="email"]').fill("kit@helix.team");
  await cold.locator('input[type="password"]').fill("demo-password-1");
  await cold.getByRole("button", { name: /Create account ⟶/ }).click();
  await cold.waitForURL(/\/w\//, { timeout: 120_000 }).catch(() => {});
  check(cold.url().includes(`/w/${wid}`), "and returns to the invite once you have an account");

  // --- pasting the link into the picker's join field ------------------------
  const paster = await (await browser.newContext({ viewport: { width: 1280, height: 860 } })).newPage();
  paster.on("pageerror", (e) => errors.add(e.message.slice(0, 140)));
  await signUp(paster, "ines@helix.team");
  const third = await inviteUrl(owner, wid, "collaborator");
  await paster.getByRole("button", { name: "Join via invite" }).click();
  await paster.getByPlaceholder(/invite link/i).fill(local(third));
  await paster.getByRole("button", { name: "Join", exact: true }).click();
  await paster.waitForURL(/\/w\//, { timeout: 60_000 }).catch(() => {});
  check(paster.url().includes(`/w/${wid}`), "pasting the link into the picker also works");

  // --- locked out, and back in ---------------------------------------------
  console.log("\nrecovery");
  await mate.evaluate(() => localStorage.clear());
  await mate.goto(`${UI}/auth`);
  await mate.getByRole("tab", { name: "Sign in" }).click();
  const forgot = mate.getByRole("button", { name: /Forgot your password/ });
  check(await forgot.count() > 0, "the sign-in page offers a way back in");
  await mate.locator('input[type="email"]').fill("grace@helix.team");
  await forgot.click();
  await mate.waitForTimeout(1200);
  await mate.locator('input[type="email"]').fill("nobody@helix.team");
  await forgot.click();
  await mate.waitForTimeout(1000);
  const said = await mate.evaluate(() => document.body.innerText);
  check(/reset link is on its way/.test(said),
    "an unregistered address is answered identically (no enumeration)");

  // The link the server would have emailed. Minted with the server's own
  // helper against the stored row, so this checks the route and the API rather
  // than the logging configuration.
  const script = [
    "import sqlite3, sys",
    "sys.path.insert(0, '.')",
    "from api.security import make_reset_token",
    `con = sqlite3.connect(r'${dbFile}')`,
    "row = con.execute('select id, pw_hash from users where email=?', ('grace@helix.team',)).fetchone()",
    "print(make_reset_token(row[0], row[1]))",
  ].join(";");
  const mint = spawnSync(join(repo, "backend", ".venv", "Scripts", "python.exe"), ["-c", script],
    { cwd: join(repo, "backend"), env: { ...process.env, HELIX_DEV: "1" }, encoding: "utf8" });
  const token = (mint.stdout || "").trim().split(/\s+/).pop() ?? "";
  if (!token) throw new Error("could not mint a reset token: " + (mint.stderr || "").slice(0, 300));

  const resetLink = `${UI}/reset-password?token=${token}`;
  await mate.goto(resetLink);
  await mate.waitForTimeout(800);
  check(/Choose a new password/.test(await mate.evaluate(() => document.body.innerText)),
    "the reset link opens a real page");

  const pw = mate.locator('input[type="password"]');
  await pw.nth(0).fill("brand-new-pass-9");
  await pw.nth(1).fill("brand-new-pass-9");
  await mate.getByRole("button", { name: /Set new password/ }).click();
  await mate.waitForTimeout(1500);
  check(/Password changed/.test(await mate.evaluate(() => document.body.innerText)),
    "the password changes");

  await mate.goto(resetLink);
  await mate.waitForTimeout(700);
  await mate.locator('input[type="password"]').nth(0).fill("second-attempt-1");
  await mate.locator('input[type="password"]').nth(1).fill("second-attempt-1");
  await mate.getByRole("button", { name: /Set new password/ }).click();
  await mate.waitForTimeout(1200);
  check(!/Password changed/.test(await mate.evaluate(() => document.body.innerText)),
    "and the same link cannot be used twice");

  await mate.goto(`${UI}/auth`);
  await mate.getByRole("tab", { name: "Sign in" }).click();
  await mate.locator('input[type="email"]').fill("grace@helix.team");
  await mate.locator('input[type="password"]').fill("brand-new-pass-9");
  await mate.getByRole("button", { name: /Enter workspace ⟶/ }).click();
  await mate.waitForURL(/\/workspaces|\/w\//, { timeout: 120_000 }).catch(() => {});
  check(/\/workspaces|\/w\//.test(mate.url()), "the new password signs in");

  await browser.close();
  // The reset-reuse step deliberately provokes a 400; only script errors count.
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
    console.log("\nEvery way in, and every way back in, works.");
  }
} catch (e) {
  console.error("FAILED:", e.message);
  code = 1;
}
await browser?.close().catch(() => {});
await Promise.all(children.map((c) => killTree(c.pid)));
process.exit(code);
