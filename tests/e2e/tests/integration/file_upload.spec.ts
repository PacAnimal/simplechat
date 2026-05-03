import { test, expect } from "@playwright/test";
import { resetDB, loginWithTestProfile, createChat, sendMessage, uploadFile, uploadTextFile } from "./helpers";

const SECRET_FILE = "secret.txt";
const SECRET_CONTENT = "The password is: elephant";

test.beforeEach(async ({ page }) => {
  await resetDB();
  await page.goto("/");
  await loginWithTestProfile(page);
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

test("OpenAI analyzes uploaded CSV — finds highest-revenue product", async ({ page }) => {
  await createChat(page, "openai", "gpt-4o-mini");

  const csv = [
    "product,units_sold,revenue",
    "Widget A,150,4500",
    "Widget B,80,6400",
    "Widget C,200,3000",
  ].join("\n");
  await uploadFile(page, "sales.csv", csv, "text/csv");

  await sendMessage(
    page,
    "Which product has the highest revenue? Reply with just the product name.",
    90_000,
  );

  const reply = page.locator('[data-testid="message-assistant"]').first();
  await expect(reply).toContainText("Widget B", { ignoreCase: true });
});

test("Anthropic analyzes uploaded CSV — finds hottest city", async ({ page }) => {
  await createChat(page, "anthropic", "claude-haiku-4-5-20251001");

  const csv = [
    "city,temperature_celsius",
    "Oslo,-5",
    "Tokyo,22",
    "Sydney,28",
    "London,12",
  ].join("\n");
  await uploadFile(page, "temperatures.csv", csv, "text/csv");

  await sendMessage(
    page,
    "Which city has the highest temperature? Reply with just the city name.",
    90_000,
  );

  const reply = page.locator('[data-testid="message-assistant"]').first();
  await expect(reply).toContainText("Sydney", { ignoreCase: true });
});

test("OpenAI reads CEO name from uploaded JSON file", async ({ page }) => {
  await createChat(page, "openai", "gpt-4o-mini");

  const json = JSON.stringify({
    company: "Acme Corp",
    ceo: "Jane Smith",
    founded: 1985,
    employees: 5000,
  });
  await uploadFile(page, "company.json", json, "application/json");

  await sendMessage(
    page,
    "Who is the CEO of this company? Reply with just their name.",
    90_000,
  );

  const reply = page.locator('[data-testid="message-assistant"]').first();
  await expect(reply).toContainText("Jane Smith", { ignoreCase: true });
});

test("Anthropic reads CEO name from uploaded JSON file", async ({ page }) => {
  await createChat(page, "anthropic", "claude-haiku-4-5-20251001");

  const json = JSON.stringify({
    company: "Globex",
    ceo: "Hank Scorpio",
    industry: "energy",
  });
  await uploadFile(page, "globex.json", json, "application/json");

  await sendMessage(
    page,
    "Who is the CEO? Reply with just their full name.",
    90_000,
  );

  const reply = page.locator('[data-testid="message-assistant"]').first();
  await expect(reply).toContainText("Hank Scorpio", { ignoreCase: true });
});
