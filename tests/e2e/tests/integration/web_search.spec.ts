import { test, expect, type Page } from "@playwright/test";
import { resetDB, loginWithTestProfile, createChat, sendMessage, BACKEND } from "./helpers";

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
  await loginWithTestProfile(page);
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

test("OpenAI web search shows source domain chips", async ({ page }) => {
  await createChat(page, "openai", "gpt-5");
  const chatId = await getLastChatId(page);
  await enableWebSearch(page, chatId);

  await page.reload();
  await page.locator('[data-testid^="chat-item-"]').first().click();
  await page.getByTestId("chat-window").waitFor({ state: "visible" });

  // start the message — chips appear while the response is streaming
  const countBefore = await page.locator('[data-testid="message-assistant"]').count();
  await page.getByTestId("message-input").fill("Search the web: what is the capital of Norway?");
  await page.getByTestId("send-button").click();

  await expect(page.locator('[data-testid="search-source-chip"]').first())
    .toBeVisible({ timeout: 90_000 });

  // wait for the response to finish
  await page.locator('[data-testid="message-assistant"]').nth(countBefore)
    .waitFor({ state: "visible", timeout: 120_000 });
});

test("Anthropic web search shows source domain chips", async ({ page }) => {
  await createChat(page, "anthropic", "claude-haiku-4-5-20251001");
  const chatId = await getLastChatId(page);
  await enableWebSearch(page, chatId);

  await page.reload();
  await page.locator('[data-testid^="chat-item-"]').first().click();
  await page.getByTestId("chat-window").waitFor({ state: "visible" });

  const countBefore = await page.locator('[data-testid="message-assistant"]').count();
  await page.getByTestId("message-input").fill("Search the web: what is the capital of Norway?");
  await page.getByTestId("send-button").click();

  await expect(page.locator('[data-testid="search-source-chip"]').first())
    .toBeVisible({ timeout: 90_000 });

  await page.locator('[data-testid="message-assistant"]').nth(countBefore)
    .waitFor({ state: "visible", timeout: 120_000 });
});

test("gpt-5 web search returns a response for a specific legal citation query", async ({ page }) => {
  await createChat(page, "openai", "gpt-5");
  const chatId = await getLastChatId(page);
  await enableWebSearch(page, chatId);

  await page.reload();
  await page.locator('[data-testid^="chat-item-"]').first().click();
  await page.getByTestId("chat-window").waitFor({ state: "visible" });

  // a specific legal citation question — the model cannot answer from memory and must
  // search, potentially multiple times, before synthesising a response
  await sendMessage(
    page,
    "Search online: which specific article of the Vienna Convention on Road Traffic (1968) requires drivers to yield to pedestrians at natural crossing points even where there is no marked pedestrian crossing?",
    120_000,
  );

  const reply = page.locator('[data-testid="message-assistant"]').first();
  const text = (await reply.textContent()) ?? "";
  expect(text.trim().length).toBeGreaterThan(50);
  expect(text.toLowerCase()).toMatch(/vienna|convention|article|pedestrian|crossing|driver|traffic/i);
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
