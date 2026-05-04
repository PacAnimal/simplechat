import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircleIcon, GlobeIcon, XIcon, ChevronDownIcon } from "lucide-react";
import { api, streamMessage } from "../lib/api";
import type { Chat, Message, ToolCallRecord } from "../types";
import { MODELS, PROVIDER_LABELS } from "../types";
import MessageBubble, { StreamingBubble, ThinkingBubble, ToolCallsBubble } from "./MessageBubble";
import MessageInput from "./MessageInput";

interface Props {
  chatId: number;
  initialMessage?: string;
}

interface StreamingState {
  content: string;
  images: { url: string; prompt: string }[];
  thinking: string;
  toolCalls: ToolCallRecord[];
}

function ModelSwitcher({ chatId, provider, model, disabled }: {
  chatId: number;
  provider: string;
  model: string;
  disabled: boolean;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const { data: remoteModels } = useQuery({
    queryKey: ["models"],
    queryFn: api.getModels,
    staleTime: 3_600_000,
  });

  const modelsFor = (p: string) => {
    const live = remoteModels?.[p];
    if (live?.length) return live.map((m) => ({ label: m.label, value: m.id }));
    return (MODELS as Record<string, { label: string; value: string }[]>)[p] ?? [];
  };

  const switchModel = useMutation({
    mutationFn: ({ p, m }: { p: string; m: string }) =>
      api.updateChat(chatId, { provider: p as Chat["provider"], model: m }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chat", chatId] });
      qc.invalidateQueries({ queryKey: ["chats"] });
      setOpen(false);
    },
  });

  // close on outside click
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => !disabled && setOpen((o) => !o)}
        className="flex items-center gap-1 text-[0.7rem] text-muted hover:text-secondary transition-colors disabled:cursor-not-allowed"
        disabled={disabled}
        title="Switch model"
      >
        {PROVIDER_LABELS[provider] ?? provider} · {model}
        <ChevronDownIcon size={10} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 bg-elevated border border-border rounded-xl shadow-xl p-3 min-w-56">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wider text-muted mb-2">Switch Model</p>
          {(["openai", "anthropic"] as const).map((p) => (
            <div key={p} className="mb-2 last:mb-0">
              <p className="text-[0.7rem] text-muted mb-1">{PROVIDER_LABELS[p]}</p>
              {modelsFor(p).map((m) => (
                <button
                  key={m.value}
                  onClick={() => switchModel.mutate({ p, m: m.value })}
                  disabled={switchModel.isPending}
                  className={`w-full text-left text-xs px-2.5 py-1.5 rounded-lg transition-colors mb-0.5 ${
                    p === provider && m.value === model
                      ? "bg-accent/15 text-accent"
                      : "text-secondary hover:bg-hover hover:text-primary"
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ChatWindow({ chatId, initialMessage }: Props) {
  const qc = useQueryClient();
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [streaming, setStreaming] = useState<StreamingState | null>(null);
  const [sending, setSending] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const { data: messages = [] } = useQuery({
    queryKey: ["messages", chatId],
    queryFn: () => api.getMessages(chatId),
  });

  const chatMeta = useQuery({
    queryKey: ["chat", chatId],
    queryFn: () => api.getChat(chatId),
  });

  const toggleWebSearch = useMutation({
    mutationFn: () =>
      api.updateChat(chatId, { web_search_enabled: !chatMeta.data?.web_search_enabled }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chat", chatId] });
      qc.invalidateQueries({ queryKey: ["chats"] });
    },
  });

  // abort on unmount
  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  // auto-scroll on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streaming?.content, streaming?.images.length, streaming?.toolCalls.length]);

  async function handleSend(content: string, attachmentIds: number[]) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setSending(true);
    setStreamError(null);
    setStreaming({ content: "", images: [], thinking: "", toolCalls: [] });

    try {
      for await (const event of streamMessage(chatId, content, attachmentIds, controller.signal)) {
        switch (event.type) {
          case "text_delta":
            setStreaming((s) => s ? { ...s, content: s.content + event.content } : s);
            break;
          case "thinking_delta":
            setStreaming((s) => s ? { ...s, thinking: s.thinking + event.content } : s);
            break;
          case "image_generated":
            setStreaming((s) =>
              s ? { ...s, images: [...s.images, { url: event.url, prompt: event.prompt }] } : s,
            );
            break;
          case "searching":
            setStreaming((s) =>
              s ? { ...s, toolCalls: [...s.toolCalls, { name: "web_search", done: false }] } : s,
            );
            break;
          case "tool_start":
            setStreaming((s) =>
              s ? { ...s, toolCalls: [...s.toolCalls, { name: event.name, done: false }] } : s,
            );
            break;
          case "tool_result":
            setStreaming((s) => {
              if (!s) return s;
              const calls = [...s.toolCalls];
              for (let i = calls.length - 1; i >= 0; i--) {
                if (calls[i].name === event.name && !calls[i].done) {
                  calls[i] = { ...calls[i], done: true, error: event.error };
                  break;
                }
              }
              return { ...s, toolCalls: calls };
            });
            break;
          case "chat_title":
            qc.invalidateQueries({ queryKey: ["chats"] });
            qc.invalidateQueries({ queryKey: ["chat", chatId] });
            break;
          case "done":
            qc.invalidateQueries({ queryKey: ["messages", chatId] });
            setStreaming(null);
            break;
          case "error":
            setStreamError(event.message);
            setStreaming(null);
            break;
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // navigated away — clean exit
      } else {
        setStreamError("Something went wrong. Please try again.");
      }
      setStreaming(null);
    } finally {
      setSending(false);
    }
  }

  const meta = chatMeta.data;

  return (
    <div className="flex flex-col h-full bg-canvas" data-testid="chat-window">
      {/* slim header */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-border/50 flex-shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <div className="min-w-0">
            <h2
              className="text-sm font-semibold text-primary truncate"
              data-testid="chat-title"
            >
              {meta?.title ?? "…"}
            </h2>
            {meta && (
              <ModelSwitcher
                chatId={chatId}
                provider={meta.provider}
                model={meta.model}
                disabled={sending}
              />
            )}
          </div>
        </div>

        <div className="flex items-center gap-1">
          {meta?.web_search_enabled && (
            <div className="flex items-center gap-1 text-xs text-accent bg-accent/10 border border-accent/20 rounded-full px-2.5 py-1">
              <GlobeIcon size={11} />
              <span>Search on</span>
            </div>
          )}

        </div>
      </header>

      {/* messages */}
      <div className="flex-1 overflow-y-auto py-8 px-4">
        {messages.length === 0 && !streaming && !streamError ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-muted text-sm">Send a message to begin</p>
          </div>
        ) : (
          <div className="space-y-6">
            {messages.map((msg: Message) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}

            {streaming && (
              <>
                {streaming.thinking && <ThinkingBubble content={streaming.thinking} />}
                {streaming.toolCalls.length > 0 && <ToolCallsBubble calls={streaming.toolCalls} />}
                <StreamingBubble content={streaming.content} images={streaming.images} />
              </>
            )}

            {streamError && (
              <div className="flex gap-3 max-w-3xl w-full mx-auto">
                <div className="w-7 h-7 flex-shrink-0" />
                <div className="flex items-center gap-2 text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-xl px-3 py-2 flex-1">
                  <AlertCircleIcon size={14} className="flex-shrink-0" />
                  <span className="flex-1">{streamError}</span>
                  <button onClick={() => setStreamError(null)} className="text-muted hover:text-primary">
                    <XIcon size={12} />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
        <div ref={bottomRef} className="h-4" />
      </div>

      {/* input */}
      <MessageInput
        onSend={handleSend}
        onUploadFile={(f) => api.uploadFile(chatId, f)}
        webSearchEnabled={meta?.web_search_enabled ?? false}
        onToggleWebSearch={() => toggleWebSearch.mutate()}
        disabled={sending}
        initialValue={initialMessage}
      />
    </div>
  );
}
