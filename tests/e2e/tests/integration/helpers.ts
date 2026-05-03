import { request, type Page } from "@playwright/test";

export const BACKEND = "http://127.0.0.1:8085";

export async function resetDB() {
  const ctx = await request.newContext();
  await ctx.post(`${BACKEND}/api/test/reset`);
  await ctx.dispose();
}

export async function createChat(
  page: Page,
  provider: "openai" | "anthropic",
  model?: string,
) {
  await page.getByTestId("new-chat-button").click();
  await page.getByTestId(`provider-${provider}`).click();
  if (model) {
    await page.getByTestId("model-select").selectOption(model);
  }
  await page.getByTestId("create-chat-button").click();
  await page.getByTestId("chat-window").waitFor({ state: "visible", timeout: 10_000 });
}

export async function sendMessage(page: Page, text: string, timeoutMs = 90_000) {
  const countBefore = await page.locator('[data-testid="message-assistant"]').count();
  await page.getByTestId("message-input").fill(text);
  await page.getByTestId("send-button").click();
  await page
    .locator('[data-testid="message-assistant"]')
    .nth(countBefore)
    .waitFor({ state: "visible", timeout: timeoutMs });
}

export async function uploadTextFile(page: Page, filename: string, content: string) {
  const input = page.locator('input[type="file"]');
  await input.setInputFiles({
    name: filename,
    mimeType: "text/plain",
    buffer: Buffer.from(content),
  });
  // wait for upload confirmation (attachment appears)
  await page.locator('[data-testid="attachment-chip"]').waitFor({ state: "visible", timeout: 10_000 });
}
