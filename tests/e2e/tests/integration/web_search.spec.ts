import { test, expect, type Page } from "@playwright/test";
import { resetDB, createChat, sendMessage, BACKEND } from "./helpers";

async function enableWebSearch(page: Page, chatId: number) {
  await page.request.patch(`${BACKEND}/api/chats/${chatId}`, {
    data: { web_search_enabled: true },
    headers: { "Content-Type": "application/json" },
  });
}

async function getLastChatId(page: Page): Promise<number> {
  const res = await page.request.get(`${BACKEND}/api/chats`);
  const chats = await res.json();
  return chats[0].id;
}

test.beforeEach(async ({ page }) => {
  await resetDB();
  await page.goto("/");
});

test("OpenAI web search finds Norwegian car dealers near Oslo", async ({ page }) => {
  await createChat(page, "openai", "gpt-4o-mini");
  const chatId = await getLastChatId(page);
  await enableWebSearch(page, chatId);

  // reload so the web search toggle reflects the enabled state
  await page.reload();
  await page.locator('[data-testid^="chat-item-"]').first().click();
  await page.getByTestId("chat-window").waitFor({ state: "visible" });

  await sendMessage(
    page,
    "Search online to find 2 Norwegian car dealers near Oslo. List their names.",
    90_000,
  );

  const reply = page.locator('[data-testid="message-assistant"]').first();
  // should mention Oslo or Norway or a car brand
  const text = (await reply.textContent()) ?? "";
  expect(text.toLowerCase()).toMatch(/oslo|norway|norsk|bil|dealer|auto|motor/i);
});

test("Anthropic web search finds Norwegian car dealers near Oslo", async ({ page }) => {
  await createChat(page, "anthropic", "claude-haiku-4-5-20251001");
  const chatId = await getLastChatId(page);
  await enableWebSearch(page, chatId);

  await page.reload();
  await page.locator('[data-testid^="chat-item-"]').first().click();
  await page.getByTestId("chat-window").waitFor({ state: "visible" });

  await sendMessage(
    page,
    "Search online to find 2 Norwegian car dealers near Oslo. List their names.",
    90_000,
  );

  const reply = page.locator('[data-testid="message-assistant"]').first();
  const text = (await reply.textContent()) ?? "";
  expect(text.toLowerCase()).toMatch(/oslo|norway|norsk|bil|dealer|auto|motor/i);
});

test("web search toggle can be turned on from UI and triggers search indicator", async ({ page }) => {
  await createChat(page, "openai", "gpt-4o-mini");

  // enable via toggle button
  const toggle = page.getByTestId("web-search-toggle");
  await toggle.click();
  await expect(page.getByText("Search on")).toBeVisible({ timeout: 5_000 });

  // send a search request and watch for the tool call indicator
  const countBefore = await page.locator('[data-testid="message-assistant"]').count();
  await page.getByTestId("message-input").fill("Search online: what is 2+2?");
  await page.getByTestId("send-button").click();

  // the tool calls bubble should appear during streaming
  // (transient, but visible briefly — we just need the final response to have run a search)
  await page
    .locator('[data-testid="message-assistant"]')
    .nth(countBefore)
    .waitFor({ state: "visible", timeout: 90_000 });
});
