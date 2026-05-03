import { test, expect } from "@playwright/test";
import { resetDB, createChat, sendMessage } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetDB();
  await page.goto("/");
});

test("Anthropic generates image when asked and it appears inline", async ({ page }) => {
  // use claude-sonnet to ensure reliable tool use
  await createChat(page, "anthropic", "claude-sonnet-4-6");
  await sendMessage(page, "Please generate an image of a red apple on a white background", 90_000);

  const img = page.locator('[data-testid="message-assistant"] [data-testid="generated-image"]').first();
  await expect(img).toBeVisible({ timeout: 10_000 });

  // image src should point to /generated/
  const src = await img.getAttribute("src");
  expect(src).toMatch(/\/generated\//);
});

test("clicking inline image opens lightbox with overlay and close button", async ({ page }) => {
  await createChat(page, "anthropic", "claude-sonnet-4-6");
  await sendMessage(page, "Generate an image of a blue circle on a white background", 90_000);

  const img = page.locator('[data-testid="message-assistant"] [data-testid="generated-image"]').first();
  await expect(img).toBeVisible({ timeout: 10_000 });

  // open lightbox
  await img.click();
  const lightbox = page.locator('[data-testid="image-lightbox"]');
  await expect(lightbox).toBeVisible({ timeout: 3_000 });

  // lightbox should contain an image
  const fullImg = lightbox.locator("img");
  await expect(fullImg).toBeVisible();

  // close with button
  const closeBtn = page.locator('[data-testid="image-lightbox-close"]');
  await expect(closeBtn).toBeVisible();
  await closeBtn.click();
  await expect(lightbox).not.toBeVisible({ timeout: 3_000 });
});

test("clicking overlay outside image closes the lightbox", async ({ page }) => {
  await createChat(page, "anthropic", "claude-sonnet-4-6");
  await sendMessage(page, "Generate an image of a green triangle", 90_000);

  const img = page.locator('[data-testid="message-assistant"] [data-testid="generated-image"]').first();
  await expect(img).toBeVisible({ timeout: 10_000 });
  await img.click();

  const lightbox = page.locator('[data-testid="image-lightbox"]');
  await expect(lightbox).toBeVisible({ timeout: 3_000 });

  // click the overlay (top-left corner, outside the image)
  await page.mouse.click(10, 10);
  await expect(lightbox).not.toBeVisible({ timeout: 3_000 });
});

test("OpenAI generates image inline and lightbox works", async ({ page }) => {
  await createChat(page, "openai", "gpt-4o-mini");
  await sendMessage(page, "Please generate an image of a simple sun", 90_000);

  const img = page.locator('[data-testid="message-assistant"] [data-testid="generated-image"]').first();
  await expect(img).toBeVisible({ timeout: 10_000 });

  await img.click();
  const lightbox = page.locator('[data-testid="image-lightbox"]');
  await expect(lightbox).toBeVisible({ timeout: 3_000 });
  await page.locator('[data-testid="image-lightbox-close"]').click();
  await expect(lightbox).not.toBeVisible({ timeout: 3_000 });
});
