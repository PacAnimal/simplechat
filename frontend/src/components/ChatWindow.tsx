import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircleIcon, GlobeIcon, XIcon, ChevronDownIcon, Menu } from "lucide-react";
import { api, modelLabel } from "../lib/api";
import { useStream } from "../lib/StreamContext";
import type { Chat, Message } from "../types";
import { MODELS, PROVIDER_LABELS } from "../types";
import MessageBubble, { StreamingBubble } from "./MessageBubble";
import MessageInput from "./MessageInput";

interface Props {
  chatId: number;
  initialMessage?: string;
  onOpenSidebar?: () => void;
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
        {PROVIDER_LABELS[provider] ?? provider} · {modelLabel(remoteModels, provider, model)}
        <ChevronDownIcon size={10} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 bg-elevated border border-border rounded-xl shadow-xl p-3 min-w-56">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wider text-muted mb-2">Switch Model</p>
          {(["openai", "anthropic", "ollama"] as const).filter((p) => modelsFor(p).length > 0).map((p) => (
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

export default function ChatWindow({ chatId, initialMessage, onOpenSidebar }: Props) {
  const qc = useQueryClient();
  const bottomRef = useRef<HTMLDivElement>(null);
  const { activeStreams, unreadChats, startStream, cancelStream, markRead } = useStream();

  const stream = activeStreams.get(chatId);
  const sending = stream?.status === "streaming";
  const streamError = stream?.status === "error" ? (stream.error ?? "Something went wrong.") : null;

  const { data: messages = [] } = useQuery({
    queryKey: ["messages", chatId],
    queryFn: () => api.getMessages(chatId),
  });

  const chatMeta = useQuery({
    queryKey: ["chat", chatId],
    queryFn: () => api.getChat(chatId),
  });

  const { data: config } = useQuery({
    queryKey: ["config"],
    queryFn: api.getConfig,
    staleTime: Infinity,
  });
  const allowSwitchingModels = config?.allow_switching_models ?? true;

  const { data: remoteModels } = useQuery({
    queryKey: ["models"],
    queryFn: api.getModels,
    staleTime: 3_600_000,
  });

  const toggleWebSearch = useMutation({
    mutationFn: () =>
      api.updateChat(chatId, { web_search_enabled: !chatMeta.data?.web_search_enabled }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chat", chatId] });
      qc.invalidateQueries({ queryKey: ["chats"] });
    },
  });

  // dismiss notification when this chat is open
  useEffect(() => {
    markRead(chatId);
  }, [chatId, markRead]);

  // also dismiss if notification fires while we're here
  const isUnread = unreadChats.has(chatId);
  useEffect(() => {
    if (isUnread) markRead(chatId);
  }, [isUnread, chatId, markRead]);

  // auto-scroll on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, stream?.content, stream?.images.length, stream?.toolCalls.length]);

  function handleSend(content: string, attachmentIds: number[]) {
    // optimistic user message
    qc.setQueryData(["messages", chatId], (old: Message[] | undefined) => [
      ...(old ?? []),
      {
        id: -Date.now(),
        chat_id: chatId,
        role: "user" as const,
        content,
        thinking: null,
        images: [],
        created_at: new Date().toISOString(),
      },
    ]);
    startStream(chatId, content, attachmentIds);
  }

  const meta = chatMeta.data;

  return (
    <div className="flex flex-col h-full bg-canvas" data-testid="chat-window">
      {/* slim header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border/50 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <button
            onClick={onOpenSidebar}
            className="wide:hidden flex-shrink-0 p-1.5 rounded-lg hover:bg-hover text-muted hover:text-primary transition-colors"
            aria-label="Open sidebar"
          >
            <Menu size={18} />
          </button>
          <div className="min-w-0">
            <h2
              className="text-sm font-semibold text-primary truncate"
              data-testid="chat-title"
            >
              {meta?.title ?? "…"}
            </h2>
            {meta && allowSwitchingModels && (
              <ModelSwitcher
                chatId={chatId}
                provider={meta.provider}
                model={meta.model}
                disabled={sending}
              />
            )}
            {meta && !allowSwitchingModels && (
              <p className="text-[0.7rem] text-muted">
                {PROVIDER_LABELS[meta.provider] ?? meta.provider} · {modelLabel(remoteModels, meta.provider, meta.model)}
              </p>
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
        {messages.length === 0 && !stream && !streamError ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-muted text-sm">Send a message to begin</p>
          </div>
        ) : (
          <div className="space-y-6">
            {messages.map((msg: Message) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}

            {stream?.status === "streaming" && (
              <StreamingBubble
                content={stream.content}
                images={stream.images}
                thinking={stream.thinking || undefined}
                toolCalls={stream.toolCalls.length > 0 ? stream.toolCalls : undefined}
              />
            )}

            {streamError && (
              <div className="flex gap-3 max-w-3xl w-full mx-auto">
                <div className="w-7 h-7 flex-shrink-0" />
                <div className="flex items-center gap-2 text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-xl px-3 py-2 flex-1">
                  <AlertCircleIcon size={14} className="flex-shrink-0" />
                  <span className="flex-1">{streamError}</span>
                  <button onClick={() => cancelStream(chatId)} className="text-muted hover:text-primary">
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
        provider={meta?.provider}
      />
    </div>
  );
}
