import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { GlobeIcon, Trash2Icon } from "lucide-react";
import { api, streamMessage } from "../lib/api";
import type { Message, ToolCallRecord } from "../types";
import { PROVIDER_LABELS } from "../types";
import MessageBubble, { StreamingBubble, ThinkingBubble, ToolCallsBubble } from "./MessageBubble";
import MessageInput from "./MessageInput";
import { cn } from "../lib/utils";

interface Props {
  chatId: number;
  onDeleted: () => void;
}

interface StreamingState {
  content: string;
  images: { url: string; prompt: string }[];
  thinking: string;
  toolCalls: ToolCallRecord[];
}

export default function ChatWindow({ chatId, onDeleted }: Props) {
  const qc = useQueryClient();
  const bottomRef = useRef<HTMLDivElement>(null);
  const [streaming, setStreaming] = useState<StreamingState | null>(null);
  const [sending, setSending] = useState(false);

  const { data: messages = [] } = useQuery({
    queryKey: ["messages", chatId],
    queryFn: () => api.getMessages(chatId),
  });

  const chatMeta = useQuery({
    queryKey: ["chat", chatId],
    queryFn: async () => {
      const chats = await api.listChats();
      return chats.find((c) => c.id === chatId) ?? null;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteChat(chatId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chats"] });
      onDeleted();
    },
  });

  const toggleWebSearch = useMutation({
    mutationFn: () =>
      api.updateChat(chatId, { web_search_enabled: !chatMeta.data?.web_search_enabled }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chat", chatId] });
      qc.invalidateQueries({ queryKey: ["chats"] });
    },
  });

  // auto-scroll on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streaming?.content]);

  async function handleSend(content: string, attachmentIds: number[]) {
    setSending(true);
    setStreaming({ content: "", images: [], thinking: "", toolCalls: [] });

    try {
      for await (const event of streamMessage(chatId, content, attachmentIds)) {
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
              // mark the last matching undone call as done
              for (let i = calls.length - 1; i >= 0; i--) {
                if (calls[i].name === event.name && !calls[i].done) {
                  calls[i] = { ...calls[i], done: true };
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
            setStreaming(null);
            console.error("Stream error:", event.message);
            break;
        }
      }
    } catch (err) {
      console.error(err);
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
              <p className="text-[0.7rem] text-muted">
                {PROVIDER_LABELS[meta.provider]} · {meta.model}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1">
          {/* web search indicator */}
          {meta?.web_search_enabled && (
            <div className="flex items-center gap-1 text-xs text-accent bg-accent/10 border border-accent/20 rounded-full px-2.5 py-1">
              <GlobeIcon size={11} />
              <span>Search on</span>
            </div>
          )}
          <button
            onClick={() => deleteMutation.mutate()}
            className="p-1.5 rounded-lg text-muted hover:text-red-400 hover:bg-hover transition-colors ml-1"
            title="Delete chat"
            data-testid="delete-chat-header"
          >
            <Trash2Icon size={15} />
          </button>
        </div>
      </header>

      {/* messages */}
      <div className="flex-1 overflow-y-auto py-8 px-4">
        {messages.length === 0 && !streaming ? (
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
      />
    </div>
  );
}
