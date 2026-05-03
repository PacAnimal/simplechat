import { test, expect, request } from "@playwright/test";

const BACKEND = "http://127.0.0.1:8084";

async function resetDB() {
  const ctx = await request.newContext();
  await ctx.post(`${BACKEND}/api/test/reset`);
  await ctx.dispose();
}

async function createChat(page: any, provider: "openai" | "anthropic" = "openai") {
  await page.getByTestId("new-chat-button").click();
  await page.getByTestId(`provider-${provider}`).click();
  await page.getByTestId("create-chat-button").click();
  await expect(page.getByTestId("chat-window")).toBeVisible({ timeout: 5000 });
}

async function sendMessage(page: any, text: string) {
  const countBefore = await page.locator('[data-testid="message-assistant"]').count();
  await page.getByTestId("message-input").fill(text);
  await page.getByTestId("send-button").click();
  // wait for a new assistant message to appear (stream completed)
  await expect(page.locator('[data-testid="message-assistant"]')).toHaveCount(
    countBefore + 1,
    { timeout: 20_000 },
  );
}

test.beforeEach(async ({ page }) => {
  await resetDB();
  await page.goto("/");
});

// ---- basic message flow ----

test("send a message to OpenAI stub and get response", async ({ page }) => {
  await createChat(page, "openai");
  await sendMessage(page, "Hello from OpenAI test");

  await expect(page.getByTestId("message-user").first()).toBeVisible();
  await expect(page.getByTestId("message-assistant").first()).toBeVisible();
  await expect(page.getByTestId("message-assistant").first()).toContainText("openai");
});

test("send a message to Anthropic stub and get response", async ({ page }) => {
  await createChat(page, "anthropic");
  await sendMessage(page, "Hello from Anthropic test");

  await expect(page.getByTestId("message-user").first()).toBeVisible();
  await expect(page.getByTestId("message-assistant").first()).toBeVisible();
  await expect(page.getByTestId("message-assistant").first()).toContainText("anthropic");
});

// ---- image generation ----

test("image generation request shows image inline", async ({ page }) => {
  await createChat(page, "openai");
  await sendMessage(page, "Please draw a picture of a cat");

  await expect(page.getByTestId("message-assistant").first()).toBeVisible();
  // the stub generates a placeholder image
  await expect(
    page.getByTestId("message-assistant").first().locator("img"),
  ).toBeVisible({ timeout: 15_000 });
});

// ---- auto-titling ----

test("chat gets auto-titled from first message", async ({ page }) => {
  await createChat(page, "openai");
  // capture title before sending
  const titleBefore = await page.getByTestId("chat-title").textContent();

  await sendMessage(page, "Tell me about the history of Rome");

  await expect(async () => {
    const title = await page.getByTestId("chat-title").textContent();
    expect(title).not.toBe(titleBefore);
  }).toPass({ timeout: 8000 });
});

// ---- recall / persistence ----

test("messages persist when navigating away and back", async ({ page }) => {
  await createChat(page, "anthropic");
  await sendMessage(page, "Remember this keyword: banana");

  // grab the chat id from the sidebar item
  const chatItem = page.locator('[data-testid^="chat-item-"]').first();
  const testId = await chatItem.getAttribute("data-testid");
  const chatId = testId!.replace("chat-item-", "");

  // navigate away (create new chat dialog, cancel)
  await page.getByTestId("new-chat-button").click();
  await page.mouse.click(10, 10);
  await page.waitForTimeout(200);

  // navigate back
  await page.getByTestId(`chat-item-${chatId}`).click();

  // original messages should still be there
  await expect(page.getByTestId("message-user").first()).toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId("message-user").first()).toContainText("banana");
});

test("chat list survives a full page reload", async ({ page }) => {
  await createChat(page, "openai");
  await sendMessage(page, "This chat should survive a reload");

  // grab title before reload
  const chatItem = page.locator('[data-testid^="chat-item-"]').first();
  const titleBefore = (await chatItem.locator("p").first().textContent()) ?? "";

  // full page reload simulates server restart (DB is file-based)
  await page.reload();
  await page.waitForLoadState("networkidle");

  const chatItemAfter = page.locator('[data-testid^="chat-item-"]').first();
  await expect(chatItemAfter).toBeVisible({ timeout: 5000 });
  const titleAfter = (await chatItemAfter.locator("p").first().textContent()) ?? "";
  expect(titleAfter).toBe(titleBefore);
});

// ---- UI basics ----

test("send button is disabled when input is empty", async ({ page }) => {
  await createChat(page, "openai");
  await expect(page.getByTestId("send-button")).toBeDisabled();
});

test("input clears after sending", async ({ page }) => {
  await createChat(page, "openai");
  await page.getByTestId("message-input").fill("test message");
  await page.getByTestId("send-button").click();
  await expect(page.getByTestId("message-input")).toHaveValue("");
});

test("web search can be toggled on and off", async ({ page }) => {
  await createChat(page, "anthropic");
  const toggle = page.getByTestId("web-search-toggle");
  await expect(toggle).toBeVisible();
  await toggle.click();
  // header indicator appears
  await expect(page.getByText("Search on")).toBeVisible({ timeout: 3000 });
  await toggle.click();
  await expect(page.getByText("Search on")).not.toBeVisible({ timeout: 3000 });
});

test("delete chat removes it from sidebar", async ({ page }) => {
  await createChat(page, "openai");
  const countBefore = await page.locator('[data-testid^="chat-item-"]').count();

  await page.getByTestId("delete-chat-header").click();
  await page.waitForTimeout(500);

  const countAfter = await page.locator('[data-testid^="chat-item-"]').count();
  expect(countAfter).toBe(countBefore - 1);
});
