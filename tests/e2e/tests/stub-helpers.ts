import { request, type Page } from "@playwright/test";

export const BACKEND = "http://127.0.0.1:8084";

export async function resetDB() {
  const ctx = await request.newContext();
  const r = await ctx.post(`${BACKEND}/api/test/reset`, {
    headers: { "X-Reset-Secret": "e2e-stub-secret" },
  });
  await ctx.dispose();
  if (!r.ok()) throw new Error(`resetDB failed: HTTP ${r.status()}`);
}

/** Create the admin profile (name=TestAdmin), log in, and inject credentials. */
export async function loginWithAdminProfile(page: Page) {
  return _loginWithProfile(page, "TestAdmin", "adminPass1");
}

/** Create a test profile, log in, and inject credentials into the page's localStorage. */
export async function loginWithTestProfile(page: Page) {
  return _loginWithProfile(page, "TestUser", "testPass1");
}

async function _loginWithProfile(page: Page, name: string, password: string) {
  const ctx = await request.newContext();
  const r1 = await ctx.post(`${BACKEND}/api/profiles`, {
    data: { name, password, avatar: 0 },
  });
  if (!r1.ok()) throw new Error(`Profile creation failed: HTTP ${r1.status()} — ${await r1.text()}`);
  const profile = await r1.json();
  const r2 = await ctx.post(`${BACKEND}/api/profiles/${profile.id}/login`, {
    data: { password },
  });
  if (!r2.ok()) throw new Error(`Login failed: HTTP ${r2.status()} — ${await r2.text()}`);
  const { token } = await r2.json();
  await ctx.dispose();

  await page.evaluate(
    ({ tok, prof }) => {
      localStorage.setItem("simplechat_token", tok);
      localStorage.setItem("simplechat_profile", JSON.stringify(prof));
    },
    { tok: token, prof: profile },
  );
  await page.reload();
  await page.waitForSelector('[data-testid="sidebar"]', { timeout: 10_000 });
}
