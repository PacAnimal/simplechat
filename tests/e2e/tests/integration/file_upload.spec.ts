import { test, expect } from "@playwright/test";
import { resetDB, createChat, sendMessage, uploadTextFile } from "./helpers";

const SECRET_FILE = "secret.txt";
const SECRET_CONTENT = "The password is: elephant";

test.beforeEach(async ({ page }) => {
  await resetDB();
  await page.goto("/");
});

test("OpenAI reads password from uploaded text file", async ({ page }) => {
  await createChat(page, "openai", "gpt-4o-mini");
  await uploadTextFile(page, SECRET_FILE, SECRET_CONTENT);

  await sendMessage(page, "What is the password mentioned in the attached file? Reply with just the password word.", 60_000);

  const reply = page.locator('[data-testid="message-assistant"]').first();
  await expect(reply).toContainText("elephant", { ignoreCase: true });
});

test("Anthropic reads password from uploaded text file", async ({ page }) => {
  await createChat(page, "anthropic", "claude-haiku-4-5-20251001");
  await uploadTextFile(page, SECRET_FILE, SECRET_CONTENT);

  await sendMessage(page, "What is the password mentioned in the attached file? Reply with just the password word.", 60_000);

  const reply = page.locator('[data-testid="message-assistant"]').first();
  await expect(reply).toContainText("elephant", { ignoreCase: true });
});

test("attachment chip appears after upload", async ({ page }) => {
  await createChat(page, "openai", "gpt-4o-mini");

  const input = page.locator('input[type="file"]');
  await input.setInputFiles({
    name: "test.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("hello world"),
  });

  const chip = page.locator('[data-testid="attachment-chip"]').first();
  await expect(chip).toBeVisible({ timeout: 10_000 });
  await expect(chip).toContainText("test.txt");
});
