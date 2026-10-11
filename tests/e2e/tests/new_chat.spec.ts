import { test, expect } from "@playwright/test";
import { resetDB, loginWithTestProfile } from "./stub-helpers";

async function createChat(page: any, provider: "openai" | "anthropic") {
  await page.getByTestId("new-chat-button").click();
  await page.getByTestId(`provider-${provider}`).click();
  await page.getByTestId("create-chat-button").click();
  await expect(page.getByTestId("new-chat-dialog")).not.toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId("chat-window")).toBeVisible({ timeout: 5000 });
}

test.beforeEach(async ({ page }) => {
  await resetDB();
  await page.goto("/");
  await loginWithTestProfile(page);
});

test("create OpenAI chat and see chat window", async ({ page }) => {
  await createChat(page, "openai");
  await expect(page.getByTestId("chat-title")).toBeVisible();
  await expect(page.getByTestId("message-input")).toBeVisible();
});

test("create Anthropic chat and see chat window", async ({ page }) => {
  await createChat(page, "anthropic");
  await expect(page.getByTestId("chat-title")).toBeVisible();
  await expect(page.getByTestId("message-input")).toBeVisible();
});

test("created chat appears in sidebar", async ({ page }) => {
  await createChat(page, "openai");
  await expect(page.locator('[data-testid^="chat-item-"]').first()).toBeVisible({ timeout: 5000 });
});

test("each cloud provider offers the chat and thinking tiers", async ({ page }) => {
  await page.getByTestId("new-chat-button").click();

  for (const provider of ["openai", "anthropic"]) {
    await page.getByTestId(`provider-${provider}`).click();
    const opts = await page.getByTestId("model-select").locator("option").allTextContents();
    expect(opts).toEqual(["Chat", "Thinking"]);
  }
});

test("can create multiple chats and they all appear in sidebar", async ({ page }) => {
  // create first chat
  await createChat(page, "openai");

  // create second chat
  await page.getByTestId("new-chat-button").click();
  await page.getByTestId("provider-anthropic").click();
  await page.getByTestId("create-chat-button").click();
  await expect(page.getByTestId("new-chat-dialog")).not.toBeVisible({ timeout: 5000 });

  // sidebar must show exactly 2 chats (DB was cleared in beforeEach)
  const chatItems = page.locator('[data-testid^="chat-item-"]');
  await expect(chatItems).toHaveCount(2, { timeout: 8000 });
});
