import { test, expect } from "@playwright/test";
import { resetDB, loginWithTestProfile, createChat, sendMessage } from "./helpers";

test.beforeEach(async ({ page }) => {
  await resetDB();
  await page.goto("/");
  await loginWithTestProfile(page);
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

test("image iteration: office cubicle scene then pink suit modification produces a new pink image", async ({ page }) => {
  await createChat(page, "openai", "gpt-4o");

  // step 1: generate the initial office scene
  await sendMessage(
    page,
    "Generate an image of a man standing in his office cubicle, facing forward, neutral expression",
    120_000,
  );

  const firstImg = page.locator('[data-testid="generated-image"]').first();
  await expect(firstImg).toBeVisible({ timeout: 10_000 });
  const firstSrc = await firstImg.getAttribute("src");
  expect(firstSrc).toMatch(/\/generated\//);

  // step 2: request the pink-suit modification in a follow-up message
  const imgCountBefore = await page.locator('[data-testid="generated-image"]').count();

  await sendMessage(
    page,
    "Now generate a new image of the same man in the same cubicle, but he is now wearing a bright pink business suit",
    120_000,
  );

  // a second generated image must appear
  const secondImg = page.locator('[data-testid="generated-image"]').nth(imgCountBefore);
  await expect(secondImg).toBeVisible({ timeout: 15_000 });

  const secondSrc = await secondImg.getAttribute("src");
  expect(secondSrc).toMatch(/\/generated\//);
  expect(secondSrc).not.toBe(firstSrc);

  // verify the second image contains a meaningful amount of pink pixels
  const pinkRatio = await page.evaluate(async (src: string) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error(`Failed to load ${src}`));
      img.src = src;
    });
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth || img.width;
    canvas.height = img.naturalHeight || img.height;
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(img, 0, 0);
    const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
    let pinkPixels = 0;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i], g = data[i + 1], b = data[i + 2];
      // pink / magenta range: high red, moderate-to-high blue, red significantly dominates green
      if (r > 170 && b > 90 && g < 160 && r - g > 40) {
        pinkPixels++;
      }
    }
    return pinkPixels / (data.length / 4);
  }, secondSrc as string);

  // at least 2 % of the image must be pink — enough to confirm the suit is there
  expect(pinkRatio).toBeGreaterThan(0.02);
});
