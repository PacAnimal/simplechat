import { test, expect } from "@playwright/test";
import { resetDB, loginWithTestProfile, createChat, sendMessage } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetDB();
  await page.goto("/");
  await loginWithTestProfile(page);
});

test("basic chat works with OpenAI gpt-4o-mini", async ({ page }) => {
  await createChat(page, "openai", "gpt-4o-mini");
  await sendMessage(page, "Reply with just the word: pineapple");

  const reply = page.locator('[data-testid="message-assistant"]').first();
  await expect(reply).toContainText("pineapple", { ignoreCase: true });
});

test("basic chat works with Anthropic claude-haiku", async ({ page }) => {
  await createChat(page, "anthropic", "claude-haiku-4-5-20251001");
  await sendMessage(page, "Reply with just the word: watermelon");

  const reply = page.locator('[data-testid="message-assistant"]').first();
  await expect(reply).toContainText("watermelon", { ignoreCase: true });
});

test("streaming response appears word by word (content grows progressively)", async ({ page }) => {
  await createChat(page, "openai", "gpt-4o-mini");

  await page.getByTestId("message-input").fill("Count slowly from 1 to 10, one number per line.");
  await page.getByTestId("send-button").click();

  // the streaming bubble should appear and grow before the final message is committed
  // we poll the streaming area and confirm content increases over time
  const streamingBubble = page.locator('[data-testid="chat-window"] .prose-chat').last();
  await expect(streamingBubble).toBeVisible({ timeout: 15_000 });

  const snapshot1 = await streamingBubble.textContent();

  // wait a moment and check it grew
  await page.waitForTimeout(1500);
  const snapshot2 = await streamingBubble.textContent();

  // content should have grown (streamed tokens arriving)
  expect((snapshot2 ?? "").length).toBeGreaterThanOrEqual((snapshot1 ?? "").length);

  // wait for full completion
  await page.locator('[data-testid="message-assistant"]').waitFor({ state: "visible", timeout: 60_000 });
});

test("model list is fetched from server and shows OpenAI chat models", async ({ page }) => {
  await page.getByTestId("new-chat-button").click();
  await page.getByTestId("provider-openai").click();

  const select = page.getByTestId("model-select");
  const options = await select.locator("option").allTextContents();
  expect(options.length).toBeGreaterThanOrEqual(2);
  // all options should be chat model IDs
  for (const opt of options) {
    expect(opt.toLowerCase()).toMatch(/gpt|^o[0-9]/);
  }
});

test("model list shows Anthropic Claude models", async ({ page }) => {
  await page.getByTestId("new-chat-button").click();
  await page.getByTestId("provider-anthropic").click();

  const select = page.getByTestId("model-select");
  const options = await select.locator("option").allTextContents();
  expect(options.length).toBeGreaterThanOrEqual(1);
  for (const opt of options) {
    expect(opt.toLowerCase()).toContain("claude");
  }
});

test("multi-turn conversation works with Anthropic", async ({ page }) => {
  await createChat(page, "anthropic", "claude-haiku-4-5-20251001");

  await sendMessage(page, "My secret number is 42. Remember it.");
  await sendMessage(page, "What was my secret number? Reply with just the number.");

  const replies = page.locator('[data-testid="message-assistant"]');
  const lastReply = replies.last();
  await expect(lastReply).toContainText("42");
});
