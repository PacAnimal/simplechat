import { request, type Page } from "@playwright/test";
import fs from "fs";

export const BACKEND = "http://127.0.0.1:8085";

export async function resetDB() {
  const ctx = await request.newContext();
  await ctx.post(`${BACKEND}/api/test/reset`, {
    headers: { "X-Reset-Secret": "e2e-integration-secret" },
  });
  await ctx.dispose();
}

export async function loginWithTestProfile(page: Page) {
  const ctx = await request.newContext();
  const r1 = await ctx.post(`${BACKEND}/api/profiles`, {
    data: { name: "TestUser", password: "testPass1", avatar: 0 },
  });
  const profile = await r1.json();
  const r2 = await ctx.post(`${BACKEND}/api/profiles/${profile.id}/login`, {
    data: { password: "testPass1" },
  });
  const { token } = await r2.json();
  await ctx.dispose();

  await page.evaluate(
    ({ tok, prof }) => {
      localStorage.setItem("simplechat_token", tok);
      localStorage.setItem("simplechat_profile", JSON.stringify(prof));
    },
    { tok: token, prof: profile },
  );
  await page.reload();
  await page.waitForSelector('[data-testid="sidebar"]', { timeout: 10_000 });
}

/** Create a profile via API and return its token (for API-driven test setup). */
export async function createProfileAndGetToken(): Promise<{ profileId: number; token: string; profile: object }> {
  const ctx = await request.newContext();
  const r1 = await ctx.post(`${BACKEND}/api/profiles`, {
    data: { name: "TestUser", password: "testPass1", avatar: 0 },
  });
  const profile = await r1.json();
  const r2 = await ctx.post(`${BACKEND}/api/profiles/${profile.id}/login`, {
    data: { password: "testPass1" },
  });
  const { token } = await r2.json();
  await ctx.dispose();
  return { profileId: profile.id, token, profile };
}

/** Create a dataset via API. Returns the dataset id. */
export async function apiCreateDataset(token: string, name: string): Promise<number> {
  const ctx = await request.newContext();
  const r = await ctx.post(`${BACKEND}/api/datasets`, {
    data: { name },
    headers: { Authorization: `Bearer ${token}` },
  });
  const ds = await r.json();
  await ctx.dispose();
  return ds.id;
}

/** Upload a file to a dataset via API. */
export async function apiUploadDatasetFile(
  token: string,
  datasetId: number,
  filepath: string,
  filename: string,
  mimeType = "application/pdf",
): Promise<void> {
  const buffer = fs.readFileSync(filepath);
  const ctx = await request.newContext();
  await ctx.post(`${BACKEND}/api/datasets/${datasetId}/files`, {
    headers: { Authorization: `Bearer ${token}` },
    multipart: {
      file: { name: filename, mimeType, buffer },
    },
  });
  await ctx.dispose();
}

/** Create a chat via API. Returns the chat id. */
export async function apiCreateChat(
  token: string,
  provider: string,
  model: string,
  datasetId?: number,
): Promise<number> {
  const ctx = await request.newContext();
  const r = await ctx.post(`${BACKEND}/api/chats`, {
    data: { provider, model, dataset_id: datasetId ?? null },
    headers: { Authorization: `Bearer ${token}` },
  });
  const chat = await r.json();
  await ctx.dispose();
  return chat.id;
}

/** Get the first available Ollama model from the backend, or null if none are available. */
export async function getOllamaModel(token: string): Promise<string | null> {
  try {
    const ctx = await request.newContext();
    const r = await ctx.get(`${BACKEND}/api/models`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const models = await r.json();
    await ctx.dispose();
    const ollamaModels: { id: string }[] = models.ollama ?? [];
    if (ollamaModels.length > 0) return ollamaModels[0].id;
  } catch {
    // ignore
  }
  return null;
}

/** Store a token+profile in the page's localStorage and wait for the sidebar. */
export async function applySession(page: Page, token: string, profile: object): Promise<void> {
  await page.evaluate(
    ({ tok, prof }) => {
      localStorage.setItem("simplechat_token", tok);
      localStorage.setItem("simplechat_profile", JSON.stringify(prof));
    },
    { tok: token, prof: profile },
  );
  await page.reload();
  await page.waitForSelector('[data-testid="sidebar"]', { timeout: 10_000 });
}

export async function createChat(
  page: Page,
  provider: "openai" | "anthropic",
  model?: string,
) {
  await page.getByTestId("new-chat-button").click();
  await page.getByTestId(`provider-${provider}`).click();
  if (model) {
    await page.getByTestId("model-select").selectOption(model);
  }
  await page.getByTestId("create-chat-button").click();
  await page.getByTestId("chat-window").waitFor({ state: "visible", timeout: 10_000 });
}

export async function sendMessage(page: Page, text: string, timeoutMs = 90_000) {
  const countBefore = await page.locator('[data-testid="message-assistant"]').count();
  await page.getByTestId("message-input").fill(text);
  await page.getByTestId("send-button").click();
  await page
    .locator('[data-testid="message-assistant"]')
    .nth(countBefore)
    .waitFor({ state: "visible", timeout: timeoutMs });
}

export async function uploadFile(
  page: Page,
  filename: string,
  content: string,
  mimeType: string = "text/plain",
) {
  const input = page.locator('input[type="file"]');
  await input.setInputFiles({
    name: filename,
    mimeType,
    buffer: Buffer.from(content),
  });
  await page.locator('[data-testid="attachment-chip"]').waitFor({ state: "visible", timeout: 10_000 });
}

export async function uploadTextFile(page: Page, filename: string, content: string) {
  await uploadFile(page, filename, content, "text/plain");
}

export async function uploadFileFromPath(page: Page, filepath: string, mimeType: string) {
  const fs = await import("fs");
  const path = await import("path");
  const buffer = fs.readFileSync(filepath);
  const filename = path.basename(filepath);
  const input = page.locator('input[type="file"]');
  await input.setInputFiles({ name: filename, mimeType, buffer });
  await page.locator('[data-testid="attachment-chip"]').waitFor({ state: "visible", timeout: 15_000 });
}
