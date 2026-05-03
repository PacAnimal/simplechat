import { request, type Page } from "@playwright/test";

export const BACKEND = "http://127.0.0.1:8084";

export async function resetDB() {
  const ctx = await request.newContext();
  await ctx.post(`${BACKEND}/api/test/reset`);
  await ctx.dispose();
}

/** Create a test profile, log in, and inject credentials into the page's localStorage. */
export async function loginWithTestProfile(page: Page) {
  const ctx = await request.newContext();
  const r1 = await ctx.post(`${BACKEND}/api/profiles`, {
    data: { name: "TestUser", password: "testpass", avatar: 0 },
  });
  const profile = await r1.json();
  const r2 = await ctx.post(`${BACKEND}/api/profiles/${profile.id}/login`, {
    data: { password: "testpass" },
  });
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
