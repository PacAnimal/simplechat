export interface Chat {
  id: number;
  title: string;
  provider: "openai" | "anthropic";
  model: string;
  web_search_enabled: boolean;
  created_at: string;
  updated_at: string;
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
  images: InlineImage[];
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
  | { type: "tool_result"; name: string; content: string }
  | { type: "image_generated"; url: string; prompt: string }
  | { type: "searching"; name: string }
  | { type: "done"; message_id: number }
  | { type: "chat_title"; title: string }
  | { type: "error"; message: string };

export interface ToolCallRecord {
  name: string;
  done: boolean;
}

export const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
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
