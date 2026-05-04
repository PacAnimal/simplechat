import { test, expect } from "@playwright/test";
import { resetDB, loginWithTestProfile } from "./stub-helpers";

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
  await loginWithTestProfile(page);
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

test("clicking inline image opens lightbox", async ({ page }) => {
  await createChat(page, "openai");
  await sendMessage(page, "Please draw a picture of a cat");

  const img = page.getByTestId("message-assistant").first().locator('[data-testid="generated-image"]');
  await expect(img).toBeVisible({ timeout: 15_000 });
  await img.click();

  await expect(page.getByTestId("image-lightbox")).toBeVisible({ timeout: 3_000 });
});

test("clicking overlay outside image closes the lightbox", async ({ page }) => {
  await createChat(page, "openai");
  await sendMessage(page, "Please draw a picture of a cat");

  const img = page.getByTestId("message-assistant").first().locator('[data-testid="generated-image"]');
  await expect(img).toBeVisible({ timeout: 15_000 });
  await img.click();
  await expect(page.getByTestId("image-lightbox")).toBeVisible({ timeout: 3_000 });

  // click the overlay in the top-left corner, well outside the image
  await page.mouse.click(10, 10);
  await expect(page.getByTestId("image-lightbox")).not.toBeVisible({ timeout: 3_000 });
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

test("input retains focus after sending via Enter", async ({ page }) => {
  await createChat(page, "openai");
  await page.getByTestId("message-input").click();
  await page.keyboard.type("hello");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("message-input")).toBeFocused();
});

test("input retains focus after clicking send button", async ({ page }) => {
  await createChat(page, "openai");
  await page.getByTestId("message-input").fill("hello");
  await page.getByTestId("send-button").click();
  await expect(page.getByTestId("message-input")).toBeFocused();
});

test("Shift+Enter inserts newline instead of sending", async ({ page }) => {
  await createChat(page, "openai");
  const input = page.getByTestId("message-input");
  await input.click();
  await page.keyboard.type("hello");
  await expect(input).toHaveValue("hello");
  await page.keyboard.press("Shift+Enter");
  // guard: newline must appear before we continue — if Shift was dropped the
  // message would have been sent and the input would be empty, failing here
  await expect(input).toHaveValue("hello\n");
  await page.keyboard.type("world");
  await expect(input).toHaveValue("hello\nworld");
  // nothing sent — no user message yet
  await expect(page.locator('[data-testid="message-user"]')).toHaveCount(0);
});

test("Ctrl+Enter inserts newline instead of sending", async ({ page }) => {
  await createChat(page, "openai");
  const input = page.getByTestId("message-input");
  await input.click();
  await page.keyboard.type("hello");
  await expect(input).toHaveValue("hello");
  await page.keyboard.press("Control+Enter");
  await expect(input).toHaveValue("hello\n");
  await page.keyboard.type("world");
  await expect(input).toHaveValue("hello\nworld");
  await expect(page.locator('[data-testid="message-user"]')).toHaveCount(0);
});

test("delete chat via sidebar removes it from sidebar", async ({ page }) => {
  await createChat(page, "openai");
  const chatItem = page.locator('[data-testid^="chat-item-"]').first();
  await expect(chatItem).toBeVisible();

  // hover to reveal the delete button, click it, then confirm
  await chatItem.hover();
  await page.locator('[data-testid^="delete-chat-"]').first().click();
  await page.locator('[data-testid^="confirm-delete-"]').first().click();

  await expect(page.locator('[data-testid^="chat-item-"]')).toHaveCount(0, { timeout: 5000 });
  await expect(page.getByTestId("chat-window")).not.toBeVisible({ timeout: 3000 });
});
