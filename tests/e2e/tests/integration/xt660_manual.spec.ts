import { test, expect } from "@playwright/test";
import path from "path";
import { resetDB, loginWithTestProfile, createChat, sendMessage, uploadFileFromPath } from "./helpers";

const MANUAL_PDF = path.resolve(__dirname, "../fixtures/xt660_service_manual.pdf");
const UNKNOWN_JPG = path.resolve(__dirname, "../fixtures/unknown.jpg");

test.beforeEach(async ({ page }) => {
  await resetDB();
  await page.goto("/");
  await loginWithTestProfile(page);
});

test("Anthropic reads spark plug gap from XT660 service manual", async ({ page }) => {
  await createChat(page, "anthropic", "claude-haiku-4-5-20251001");
  await uploadFileFromPath(page, MANUAL_PDF, "application/pdf");

  await sendMessage(
    page,
    "What is the recommended spark plug gap? Reply with just the measurement.",
    90_000,
  );

  const reply = page.locator('[data-testid="message-assistant"]').first();
  // manual specifies 0.7–0.8 mm (0.028–0.031 in)
  await expect(reply).toContainText("0.7");
  await expect(reply).toContainText("0.8");
});

test("OpenAI reads spark plug gap from XT660 service manual", async ({ page }) => {
  await createChat(page, "openai", "gpt-4o-mini");
  await uploadFileFromPath(page, MANUAL_PDF, "application/pdf");

  await sendMessage(
    page,
    "What is the recommended spark plug gap? Reply with just the measurement.",
    90_000,
  );

  const reply = page.locator('[data-testid="message-assistant"]').first();
  await expect(reply).toContainText("0.7");
  await expect(reply).toContainText("0.8");
});

test("Anthropic identifies unknown.jpg as a motorcycle", async ({ page }) => {
  await createChat(page, "anthropic", "claude-haiku-4-5-20251001");

  const fs = await import("fs");
  const buffer = fs.readFileSync(UNKNOWN_JPG);
  await page.evaluate(
    ({ b64 }: { b64: string }) => {
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const file = new File([bytes], "unknown.jpg", { type: "image/jpeg" });
      const dt = new DataTransfer();
      dt.items.add(file);
      const el = document.querySelector('[data-testid="message-input"]') as HTMLElement;
      el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    },
    { b64: buffer.toString("base64") },
  );
  await page.locator('[data-testid="attachment-chip"]').waitFor({ state: "visible", timeout: 15_000 });

  await sendMessage(page, "What is this? Describe it briefly.", 90_000);

  const reply = page.locator('[data-testid="message-assistant"]').first();
  await expect(reply).toContainText("motorcycle", { ignoreCase: true });
});

test("OpenAI identifies unknown.jpg as a motorcycle", async ({ page }) => {
  await createChat(page, "openai", "gpt-4o-mini");

  const fs = await import("fs");
  const buffer = fs.readFileSync(UNKNOWN_JPG);
  await page.evaluate(
    ({ b64 }: { b64: string }) => {
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const file = new File([bytes], "unknown.jpg", { type: "image/jpeg" });
      const dt = new DataTransfer();
      dt.items.add(file);
      const el = document.querySelector('[data-testid="message-input"]') as HTMLElement;
      el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    },
    { b64: buffer.toString("base64") },
  );
  await page.locator('[data-testid="attachment-chip"]').waitFor({ state: "visible", timeout: 15_000 });

  await sendMessage(page, "What is this? Describe it briefly.", 90_000);

  const reply = page.locator('[data-testid="message-assistant"]').first();
  await expect(reply).toContainText("motorcycle", { ignoreCase: true });
});
