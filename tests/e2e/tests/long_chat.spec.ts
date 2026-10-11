import { test, expect, type Page } from "@playwright/test";
import { resetDB, loginWithTestProfile } from "./stub-helpers";

const COUNT = 300;

// A long history, served in place of the real one so the test needs no 300 stub round trips.
function history(chatId: number) {
  return Array.from({ length: COUNT }, (_, i) => ({
    id: i + 1,
    chat_id: chatId,
    role: i % 2 === 0 ? "user" : "assistant",
    content: `message ${i + 1}`,
    thinking: null,
    tool_calls: null,
    images: [],
    attachments: [],
    created_at: new Date(Date.UTC(2026, 0, 1, 0, i)).toISOString(),
  }));
}

// A reply the test feeds one event at a time, so what arrives and when is decided here rather than by a stub.
async function controlledReplies(page: Page) {
  await page.addInitScript(() => {
    const realFetch = window.fetch.bind(window);
    const w = window as unknown as { __reply?: ReadableStreamDefaultController<Uint8Array> };
    window.fetch = (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (init?.method !== "POST" || !/\/chats\/\d+\/messages$/.test(url)) return realFetch(input, init);
      const body = new ReadableStream<Uint8Array>({ start: (c) => { w.__reply = c; } });
      return Promise.resolve(new Response(body, { headers: { "Content-Type": "text/event-stream" } }));
    };
  });
}

async function replyWith(page: Page, event: object) {
  await page.evaluate((e) => {
    const w = window as unknown as { __reply: ReadableStreamDefaultController<Uint8Array> };
    w.__reply.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(e)}\n\n`));
  }, event);
}

// opens a chat with a long history; what the returned list holds is what the server answers with
async function openLongChat(page: Page) {
  let served: ReturnType<typeof history> | null = null;
  await page.route(/\/api\/chats\/(\d+)\/messages$/, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    served ??= history(Number(/chats\/(\d+)\/messages/.exec(route.request().url())![1]));
    await route.fulfill({ json: served });
  });

  await page.getByTestId("new-chat-button").click();
  await page.getByTestId("provider-openai").click();
  await page.getByTestId("create-chat-button").click();
  await expect(page.getByTestId("chat-window")).toBeVisible({ timeout: 5000 });
  await expect(page.getByText(`message ${COUNT}`, { exact: true })).toBeInViewport({ timeout: 5000 });
  return served!;
}

// a long reply, so each event grows the page by more than the viewport
const paragraph = (n: number) => `${"line\n\n".repeat(30)}paragraph ${n}\n\n`;

const distanceFromEnd = (page: Page) =>
  page.getByTestId("message-scroll").evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight);

async function sendAndStartReply(page: Page) {
  await page.getByTestId("message-input").fill("go on");
  await page.getByTestId("send-button").click();
  await replyWith(page, { type: "user_message_saved", message_id: COUNT + 1 });
  await replyWith(page, { type: "text_delta", content: paragraph(1) });
  await expect(page.getByText("paragraph 1", { exact: true })).toBeInViewport();
}

test.beforeEach(async ({ page }) => {
  await controlledReplies(page);
  await resetDB();
  await page.goto("/");
  await loginWithTestProfile(page);
});

// only what is near the viewport is mounted, and the chat opens at its newest message
test("a long chat mounts only what is near the viewport and opens at the end", async ({ page }) => {
  await openLongChat(page);
  await expect(page.getByText("message 1", { exact: true })).toHaveCount(0);
  const mounted = await page.locator('[data-testid^="message-"]:not([data-testid="message-input"])').count();
  expect(mounted).toBeLessThan(COUNT / 4);
});

// a reply being written is followed while the reader stays at the end
test("a reply is followed while the reader is at the end", async ({ page }) => {
  await openLongChat(page);
  await sendAndStartReply(page);

  await replyWith(page, { type: "text_delta", content: paragraph(2) });
  await expect(page.getByText("paragraph 2", { exact: true })).toBeInViewport();
  expect(await distanceFromEnd(page)).toBeLessThan(80);
});

// scrolling up while the reply is written leaves the reader where they went
test("scrolling up while a reply is written is not undone by it", async ({ page }) => {
  await openLongChat(page);
  await sendAndStartReply(page);

  const scroller = page.getByTestId("message-scroll");
  await scroller.hover();
  await page.mouse.wheel(0, -1500);
  await expect.poll(() => distanceFromEnd(page)).toBeGreaterThan(1000);
  const before = await scroller.evaluate((el) => el.scrollTop);

  await replyWith(page, { type: "text_delta", content: paragraph(2) });
  await expect(page.getByText("paragraph 2", { exact: true })).toBeAttached();
  expect(await scroller.evaluate((el) => el.scrollTop)).toBe(before);
  await expect(page.getByText("paragraph 2", { exact: true })).not.toBeInViewport();

  // scrolling back down mid-reply picks the following up again
  await page.mouse.wheel(0, 100_000);
  await expect.poll(() => distanceFromEnd(page)).toBeLessThan(80);
  await replyWith(page, { type: "text_delta", content: paragraph(3) });
  await expect(page.getByText("paragraph 3", { exact: true })).toBeInViewport();
  expect(await distanceFromEnd(page)).toBeLessThan(80);
});

// the finished reply replacing the one being written does not move a reader who scrolled away
test("a reply finishing does not pull a reader who scrolled up back down", async ({ page }) => {
  const served = await openLongChat(page);
  await sendAndStartReply(page);

  const scroller = page.getByTestId("message-scroll");
  await scroller.hover();
  await page.mouse.wheel(0, -1500);
  await expect.poll(() => distanceFromEnd(page)).toBeGreaterThan(1000);
  const before = await scroller.evaluate((el) => el.scrollTop);

  // the refetch that follows a finished reply finds the exchange saved
  const at = served[served.length - 1].created_at;
  served.push(
    { ...served[0], id: COUNT + 1, role: "user", content: "go on", created_at: at },
    { ...served[1], id: COUNT + 2, role: "assistant", content: paragraph(1), created_at: at },
  );
  const refetched = page.waitForResponse((r) => r.request().method() === "GET" && /\/messages$/.test(r.url()));
  await replyWith(page, { type: "done", message_id: COUNT + 2 });
  await refetched;
  await expect(page.getByTestId("message-assistant").filter({ hasText: "paragraph 1" })).toBeAttached();
  expect(await scroller.evaluate((el) => el.scrollTop)).toBe(before);
});
