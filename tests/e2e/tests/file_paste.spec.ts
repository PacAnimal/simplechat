import { test, expect } from "@playwright/test";
import { resetDB, loginWithTestProfile } from "./stub-helpers";

// 1×1 transparent PNG
const STUB_PNG_B64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

async function createChat(page: any) {
  await page.getByTestId("new-chat-button").click();
  await page.getByTestId("provider-openai").click();
  await page.getByTestId("create-chat-button").click();
  await expect(page.getByTestId("chat-window")).toBeVisible({ timeout: 5_000 });
}

/** Dispatch a synthetic paste event carrying a PNG file onto the message input. */
async function pasteImage(page: any, b64: string, filename = "screenshot.png") {
  await page.evaluate(
    ({ b64, filename }: { b64: string; filename: string }) => {
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const file = new File([bytes], filename, { type: "image/png" });
      const dt = new DataTransfer();
      dt.items.add(file);
      const el = document.querySelector('[data-testid="message-input"]') as HTMLElement;
      el.dispatchEvent(
        new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }),
      );
    },
    { b64, filename },
  );
}

test.beforeEach(async ({ page }) => {
  await resetDB();
  await page.goto("/");
  await loginWithTestProfile(page);
});

test("pasting an image shows attachment chip with thumbnail", async ({ page }) => {
  await createChat(page);
  await pasteImage(page, STUB_PNG_B64);

  const chip = page.getByTestId("attachment-chip");
  await expect(chip).toBeVisible({ timeout: 10_000 });
  await expect(chip.locator("img")).toBeVisible();
  await expect(chip).toContainText("screenshot.png");
});

test("pasting multiple images shows multiple chips", async ({ page }) => {
  await createChat(page);
  await pasteImage(page, STUB_PNG_B64, "first.png");
  await expect(page.getByTestId("attachment-chip")).toHaveCount(1, { timeout: 10_000 });
  await pasteImage(page, STUB_PNG_B64, "second.png");
  await expect(page.getByTestId("attachment-chip")).toHaveCount(2, { timeout: 10_000 });
});

test("removing an attachment chip clears it", async ({ page }) => {
  await createChat(page);
  await pasteImage(page, STUB_PNG_B64);
  await expect(page.getByTestId("attachment-chip")).toBeVisible({ timeout: 10_000 });

  await page.getByTestId("attachment-chip").locator("button").click();
  await expect(page.getByTestId("attachment-chip")).not.toBeVisible({ timeout: 3_000 });
});

test("send button enabled with attachment but no text", async ({ page }) => {
  await createChat(page);
  await pasteImage(page, STUB_PNG_B64);
  await expect(page.getByTestId("attachment-chip")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("send-button")).not.toBeDisabled();
});

test("message with pasted image sends and chip clears", async ({ page }) => {
  await createChat(page);
  await pasteImage(page, STUB_PNG_B64);
  await expect(page.getByTestId("attachment-chip")).toBeVisible({ timeout: 10_000 });

  const countBefore = await page.locator('[data-testid="message-assistant"]').count();
  await page.getByTestId("send-button").click();
  await expect(page.locator('[data-testid="message-assistant"]')).toHaveCount(countBefore + 1, {
    timeout: 20_000,
  });
  await expect(page.getByTestId("attachment-chip")).not.toBeVisible();
});

test("image file attached via file picker shows thumbnail", async ({ page }) => {
  await createChat(page);

  const bytes = Buffer.from(STUB_PNG_B64, "base64");
  await page.locator('input[type="file"]').setInputFiles({
    name: "photo.png",
    mimeType: "image/png",
    buffer: bytes,
  });

  const chip = page.getByTestId("attachment-chip");
  await expect(chip).toBeVisible({ timeout: 10_000 });
  await expect(chip.locator("img")).toBeVisible();
});

test("plain text paste goes into input, not attachment", async ({ page }) => {
  await createChat(page);
  // focus the input and paste plain text via keyboard
  await page.getByTestId("message-input").click();
  await page.keyboard.insertText("hello world");

  await expect(page.getByTestId("message-input")).toHaveValue("hello world");
  await expect(page.getByTestId("attachment-chip")).not.toBeVisible();
});
