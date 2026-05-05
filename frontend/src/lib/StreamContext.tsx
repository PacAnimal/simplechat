import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { streamMessage } from "./api";
import type { ToolCallRecord } from "../types";

export type ActiveStream = {
  status: "streaming" | "error";
  content: string;
  thinking: string;
  images: { url: string; prompt: string }[];
  toolCalls: ToolCallRecord[];
  error?: string;
};

type StreamContextValue = {
  activeStreams: Map<number, ActiveStream>;
  unreadChats: Set<number>;
  startStream: (chatId: number, content: string, attachmentIds: number[]) => void;
  cancelStream: (chatId: number) => void;
  markRead: (chatId: number) => void;
};

const StreamContext = createContext<StreamContextValue | null>(null);

export function StreamProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const [activeStreams, setActiveStreams] = useState<Map<number, ActiveStream>>(new Map());
  const [unreadChats, setUnreadChats] = useState<Set<number>>(new Set());
  const controllers = useRef<Map<number, AbortController>>(new Map());

  useEffect(() => {
    const ctls = controllers.current;
    return () => { ctls.forEach((c) => c.abort()); };
  }, []);

  const cancelStream = useCallback((chatId: number) => {
    controllers.current.get(chatId)?.abort();
    controllers.current.delete(chatId);
    setActiveStreams((prev) => {
      const next = new Map(prev);
      next.delete(chatId);
      return next;
    });
  }, []);

  const markRead = useCallback((chatId: number) => {
    setUnreadChats((prev) => {
      if (!prev.has(chatId)) return prev;
      const next = new Set(prev);
      next.delete(chatId);
      return next;
    });
  }, []);

  const startStream = useCallback(
    async (chatId: number, content: string, attachmentIds: number[]) => {
      controllers.current.get(chatId)?.abort();

      const controller = new AbortController();
      controllers.current.set(chatId, controller);

      setActiveStreams((prev) =>
        new Map(prev).set(chatId, {
          status: "streaming",
          content: "",
          thinking: "",
          images: [],
          toolCalls: [],
        }),
      );
      setUnreadChats((prev) => {
        if (!prev.has(chatId)) return prev;
        const next = new Set(prev);
        next.delete(chatId);
        return next;
      });

      try {
        for await (const event of streamMessage(chatId, content, attachmentIds, controller.signal)) {
          if (controller.signal.aborted) break;

          switch (event.type) {
            case "text_delta":
              setActiveStreams((prev) => {
                const entry = prev.get(chatId);
                if (!entry) return prev;
                return new Map(prev).set(chatId, { ...entry, content: entry.content + event.content });
              });
              break;
            case "thinking_delta":
              setActiveStreams((prev) => {
                const entry = prev.get(chatId);
                if (!entry) return prev;
                return new Map(prev).set(chatId, { ...entry, thinking: entry.thinking + event.content });
              });
              break;
            case "image_generated":
              setActiveStreams((prev) => {
                const entry = prev.get(chatId);
                if (!entry) return prev;
                return new Map(prev).set(chatId, {
                  ...entry,
                  images: [...entry.images, { url: event.url, prompt: event.prompt }],
                });
              });
              break;
            case "searching":
              setActiveStreams((prev) => {
                const entry = prev.get(chatId);
                if (!entry) return prev;
                return new Map(prev).set(chatId, {
                  ...entry,
                  toolCalls: [...entry.toolCalls, { name: "web_search", done: false }],
                });
              });
              break;
            case "tool_start":
              setActiveStreams((prev) => {
                const entry = prev.get(chatId);
                if (!entry) return prev;
                return new Map(prev).set(chatId, {
                  ...entry,
                  toolCalls: [...entry.toolCalls, { name: event.name, done: false }],
                });
              });
              break;
            case "tool_result":
              setActiveStreams((prev) => {
                const entry = prev.get(chatId);
                if (!entry) return prev;
                const calls = [...entry.toolCalls];
                for (let i = calls.length - 1; i >= 0; i--) {
                  if (calls[i].name === event.name && !calls[i].done) {
                    calls[i] = { ...calls[i], done: true, error: event.error };
                    break;
                  }
                }
                return new Map(prev).set(chatId, { ...entry, toolCalls: calls });
              });
              break;
            case "chat_title":
              qc.invalidateQueries({ queryKey: ["chats"] });
              qc.invalidateQueries({ queryKey: ["chat", chatId] });
              break;
            case "done":
              qc.invalidateQueries({ queryKey: ["messages", chatId] });
              controllers.current.delete(chatId);
              setActiveStreams((prev) => {
                const next = new Map(prev);
                next.delete(chatId);
                return next;
              });
              setUnreadChats((prev) => new Set(prev).add(chatId));
              break;
            case "error":
              setActiveStreams((prev) => {
                const entry = prev.get(chatId);
                if (!entry) return prev;
                return new Map(prev).set(chatId, {
                  ...entry,
                  status: "error",
                  error: event.message,
                });
              });
              controllers.current.delete(chatId);
              break;
          }
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // cancelled
        } else {
          setActiveStreams((prev) => {
            const entry = prev.get(chatId);
            if (!entry) return prev;
            return new Map(prev).set(chatId, {
              ...entry,
              status: "error",
              error: "Something went wrong. Please try again.",
            });
          });
          controllers.current.delete(chatId);
        }
      }
    },
    [qc],
  );

  return (
    <StreamContext.Provider value={{ activeStreams, unreadChats, startStream, cancelStream, markRead }}>
      {children}
    </StreamContext.Provider>
  );
}

export function useStream() {
  const ctx = useContext(StreamContext);
  if (!ctx) throw new Error("useStream must be used within StreamProvider");
  return ctx;
}
