import type { Attachment, Chat, Message, MessageSearchResult, Profile, StreamEvent } from "../types";

const BASE = "/api";
const TOKEN_KEY = "simplechat_token";
const PROFILE_KEY = "simplechat_profile";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(PROFILE_KEY);
}

export function getStoredProfile(): Profile | null {
  const raw = localStorage.getItem(PROFILE_KEY);
  try {
    return raw ? (JSON.parse(raw) as Profile) : null;
  } catch {
    return null;
  }
}

export function storeProfile(profile: Profile): void {
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}`, ...extra } : extra;
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers = authHeaders(body ? { "Content-Type": "application/json" } : {});
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    if (res.status === 401) {
      clearToken();
      window.dispatchEvent(new Event("simplechat:unauthorized"));
      throw new Error("UNAUTHORIZED");
    }
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export type ModelsResponse = Record<string, { id: string; label: string }[]>;

/** Look up the display label for a model ID; falls back to the raw ID. */
export function modelLabel(
  models: ModelsResponse | undefined,
  provider: string,
  modelId: string,
): string {
  return models?.[provider]?.find((m) => m.id === modelId)?.label ?? modelId;
}

export const api = {
  getConfig: () => req<{ can_create_profile: boolean; password_min_length: number; allow_switching_models: boolean }>("GET", "/config"),
  // profiles (no auth required)
  listProfiles: () => req<Profile[]>("GET", "/profiles"),
  createProfile: (name: string, password: string, avatar: number) =>
    req<Profile>("POST", "/profiles", { name, password, avatar }),
  loginProfile: (profileId: number, password: string) =>
    req<{ token: string; profile: Profile }>("POST", `/profiles/${profileId}/login`, { password }),
  deleteProfile: (profileId: number) => req<void>("DELETE", `/profiles/${profileId}`),
  updateAvatar: (profileId: number, avatar: number, avatar_color: string | null) =>
    req<Profile>("PATCH", `/profiles/${profileId}/avatar`, { avatar, avatar_color }),
  updateProfileName: (profileId: number, name: string) =>
    req<Profile>("PATCH", `/profiles/${profileId}/name`, { name }),
  changePassword: (profileId: number, current_password: string, new_password: string) =>
    req<void>("POST", `/profiles/${profileId}/change-password`, { current_password, new_password }),

  // models
  getModels: () => req<ModelsResponse>("GET", "/models"),

  // chats
  listChats: () => req<Chat[]>("GET", "/chats"),
  getChat: (id: number) => req<Chat>("GET", `/chats/${id}`),
  createChat: (provider: string, model: string, title?: string) =>
    req<Chat>("POST", "/chats", { provider, model, title }),
  updateChat: (id: number, patch: Partial<Chat>) => req<Chat>("PATCH", `/chats/${id}`, patch),
  deleteChat: (id: number) => req<void>("DELETE", `/chats/${id}`),
  getMessages: (chatId: number) => req<Message[]>("GET", `/chats/${chatId}/messages`),
  searchMessages: (q: string) => req<MessageSearchResult[]>("GET", `/chats/messages/search?q=${encodeURIComponent(q)}`),
  uploadFile: async (chatId: number, file: File): Promise<Attachment> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/chats/${chatId}/files`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });
    if (!res.ok) {
      if (res.status === 401) {
        clearToken();
        window.dispatchEvent(new Event("simplechat:unauthorized"));
        throw new Error("UNAUTHORIZED");
      }
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
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ content, attachment_ids: attachmentIds }),
    signal,
  });

  if (!res.ok) {
    if (res.status === 401) {
      clearToken();
      window.dispatchEvent(new Event("simplechat:unauthorized"));
      throw new Error("UNAUTHORIZED");
    }
    throw new Error(`Stream failed: ${res.status}`);
  }
  if (!res.body) throw new Error("Stream failed: no body");

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
