import type { Chat, Message, Attachment, StreamEvent } from "../types";

const BASE = "/api";

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  getModels: () => req<Record<string, { id: string; label: string }[]>>("GET", "/models"),
  listChats: () => req<Chat[]>("GET", "/chats"),
  getChat: (id: number) => req<Chat>("GET", `/chats/${id}`),
  createChat: (provider: string, model: string, title?: string) =>
    req<Chat>("POST", "/chats", { provider, model, title }),
  updateChat: (id: number, patch: Partial<Chat>) => req<Chat>("PATCH", `/chats/${id}`, patch),
  deleteChat: (id: number) => req<void>("DELETE", `/chats/${id}`),
  getMessages: (chatId: number) => req<Message[]>("GET", `/chats/${chatId}/messages`),
  uploadFile: async (chatId: number, file: File): Promise<Attachment> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/chats/${chatId}/files`, { method: "POST", body: form });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(`${res.status}: ${text}`);
    }
    return res.json();
  },
};

export async function* streamMessage(
  chatId: number,
  content: string,
  attachmentIds: number[] = [],
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${BASE}/chats/${chatId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, attachment_ids: attachmentIds }),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Stream failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            yield JSON.parse(line.slice(6)) as StreamEvent;
          } catch {
            // ignore malformed events
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
