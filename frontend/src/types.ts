export interface Profile {
  id: number;
  name: string;
  avatar: number;
  avatar_color: string | null;
  created_at: string;
}

export interface Chat {
  id: number;
  title: string;
  provider: "openai" | "anthropic" | "ollama";
  model: string;
  web_search_enabled: boolean;
  dataset_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface DatasetFile {
  id: number;
  dataset_id: number;
  filename: string;
  mime_type: string;
  size: number;
  created_at: string;
}

export interface Dataset {
  id: number;
  name: string;
  created_at: string;
  index_status: "ready" | "indexing" | "failed";
  indexed_chunks: number;
  files: DatasetFile[];
}

export interface InlineImage {
  url: string;
  prompt: string;
}

export interface Message {
  id: number;
  chat_id: number;
  role: "user" | "assistant";
  content: string;
  thinking: string | null;
  images: InlineImage[];
  attachments: Attachment[];
  created_at: string;
}

export interface MessageSearchResult {
  message_id: number;
  chat_id: number;
  chat_title: string;
  chat_provider: string;
  chat_model: string;
  role: string;
  content: string;
  created_at: string;
}

export interface Attachment {
  id: number;
  chat_id: number;
  message_id: number | null;
  filename: string;
  mime_type: string;
  size: number;
  created_at: string;
}

export type StreamEvent =
  | { type: "text_delta"; content: string }
  | { type: "thinking_delta"; content: string }
  | { type: "tool_start"; name: string }
  | { type: "tool_result"; name: string; content: string; error?: string; sources?: string[] }
  | { type: "image_generated"; url: string; prompt: string }
  | { type: "searching"; name: string }
  | { type: "user_message_saved"; message_id: number }
  | { type: "done"; message_id: number }
  | { type: "chat_title"; title: string }
  | { type: "error"; message: string };

export interface ToolCallRecord {
  name: string;
  done: boolean;
  error?: string;
  sources?: string[];
}

export const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  ollama: "Ollama",
};

export const MODELS: Record<string, { label: string; value: string }[]> = {
  openai: [
    { label: "GPT-4o", value: "gpt-4o" },
    { label: "GPT-4o mini", value: "gpt-4o-mini" },
    { label: "GPT-4 Turbo", value: "gpt-4-turbo" },
    { label: "o1-mini", value: "o1-mini" },
  ],
  anthropic: [
    { label: "Claude Opus 4.7", value: "claude-opus-4-7" },
    { label: "Claude Sonnet 4.6", value: "claude-sonnet-4-6" },
    { label: "Claude Haiku 4.5", value: "claude-haiku-4-5-20251001" },
  ],
};

export const AVATARS: { emoji: string; bg: string }[] = [
  { emoji: "🦊", bg: "#c2410c" },
  { emoji: "🐻", bg: "#78350f" },
  { emoji: "🐱", bg: "#b45309" },
  { emoji: "🐶", bg: "#92400e" },
  { emoji: "🐼", bg: "#374151" },
  { emoji: "🦁", bg: "#a16207" },
  { emoji: "🐯", bg: "#c2410c" },
  { emoji: "🦋", bg: "#6d28d9" },
  { emoji: "🐸", bg: "#065f46" },
  { emoji: "🦄", bg: "#9d174d" },
  { emoji: "🐲", bg: "#0f766e" },
  { emoji: "🦅", bg: "#1d4ed8" },
  { emoji: "🐺", bg: "#4c1d95" },
  { emoji: "🦑", bg: "#0369a1" },
  { emoji: "🦩", bg: "#be185d" },
  { emoji: "🦜", bg: "#166534" },
  { emoji: "🐙", bg: "#7e22ce" },
  { emoji: "🦈", bg: "#075985" },
  { emoji: "🦝", bg: "#3f3f46" },
  { emoji: "🐉", bg: "#991b1b" },
  { emoji: "🦘", bg: "#b45309" },
  { emoji: "🦔", bg: "#6b3a2a" },
  { emoji: "🦦", bg: "#7c4f1a" },
  { emoji: "🦫", bg: "#5b3a12" },
  { emoji: "🦥", bg: "#7d6149" },
  { emoji: "🦚", bg: "#0d6e72" },
  { emoji: "🦉", bg: "#6b4c1e" },
  { emoji: "🐢", bg: "#3a6b35" },
  { emoji: "🐊", bg: "#4a6741" },
  { emoji: "🐋", bg: "#1e3a8a" },
  { emoji: "🦭", bg: "#334155" },
  { emoji: "🐘", bg: "#4b5563" },
  { emoji: "🦒", bg: "#9a6d1e" },
  { emoji: "🦌", bg: "#7c4a1e" },
  { emoji: "🦇", bg: "#3b0764" },
  { emoji: "🐝", bg: "#92400e" },
  { emoji: "🐞", bg: "#991b1b" },
  { emoji: "🐠", bg: "#c2410c" },
  { emoji: "🦞", bg: "#be123c" },
  { emoji: "🦀", bg: "#b91c1c" },
  { emoji: "🐬", bg: "#0c4a6e" },
  { emoji: "🐓", bg: "#7c2d12" },
  { emoji: "🐿️", bg: "#6b3a1a" },
  { emoji: "🐪", bg: "#a16207" },
  { emoji: "🦏", bg: "#57534e" },
  { emoji: "🐎", bg: "#422006" },
  { emoji: "🐖", bg: "#be185d" },
  { emoji: "🐇", bg: "#1e3a5f" },
  { emoji: "🦗", bg: "#365314" },
  { emoji: "🐡", bg: "#0369a1" },
];
