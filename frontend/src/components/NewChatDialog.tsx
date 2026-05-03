import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { XIcon, SparklesIcon } from "lucide-react";
import { api } from "../lib/api";
import type { Chat } from "../types";
import { MODELS, PROVIDER_LABELS } from "../types";

interface Props {
  onCreated: (chat: Chat) => void;
  onClose: () => void;
}

const PROVIDER_ICONS: Record<string, string> = {
  openai: "🟢",
  anthropic: "🟠",
};

const LAST_PROVIDER_KEY = "simplechat_last_provider";

function getLastProvider(): "openai" | "anthropic" {
  try {
    const v = localStorage.getItem(LAST_PROVIDER_KEY);
    if (v === "openai" || v === "anthropic") return v;
  } catch { /* localStorage unavailable (e.g. private browsing) */ }
  return "anthropic";
}

export default function NewChatDialog({ onCreated, onClose }: Props) {
  const qc = useQueryClient();
  const [provider, setProvider] = useState<"openai" | "anthropic">(getLastProvider);
  const [model, setModel] = useState("");

  const { data: remoteModels } = useQuery({
    queryKey: ["models"],
    queryFn: api.getModels,
    staleTime: 3_600_000, // 1 hour
  });

  const modelsFor = (p: "openai" | "anthropic") => {
    const live = remoteModels?.[p];
    if (live?.length) return live.map((m) => ({ label: m.label, value: m.id }));
    return MODELS[p];
  };

  // sync model when provider or remote models change
  useEffect(() => {
    const options = modelsFor(provider);
    if (!model || !options.find((o) => o.value === model)) {
      setModel(options[0]?.value ?? ""); // eslint-disable-line react-hooks/set-state-in-effect
    }
  }, [provider, remoteModels]); // eslint-disable-line react-hooks/exhaustive-deps

  const mutation = useMutation({
    mutationFn: () => api.createChat(provider, model),
    onSuccess: (chat) => {
      qc.invalidateQueries({ queryKey: ["chats"] });
      onCreated(chat);
    },
  });

  function handleProviderChange(p: "openai" | "anthropic") {
    setProvider(p);
    try { localStorage.setItem(LAST_PROVIDER_KEY, p); } catch { /* ignore */ }
    const options = modelsFor(p);
    setModel(options[0]?.value ?? "");
  }

  // close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const options = modelsFor(provider);

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      data-testid="new-chat-dialog"
    >
      <div className="bg-elevated border border-border w-full max-w-sm rounded-2xl shadow-2xl animate-fade-in">
        {/* header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-border">
          <div className="flex items-center gap-2">
            <SparklesIcon size={16} className="text-accent" />
            <h2 className="text-base font-semibold text-primary">New Chat</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-hover text-muted hover:text-primary transition-colors"
          >
            <XIcon size={16} />
          </button>
        </div>

        <div className="px-5 py-5 space-y-5">
          {/* provider */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-muted mb-2.5">
              Provider
            </label>
            <div className="grid grid-cols-2 gap-2">
              {(["openai", "anthropic"] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => handleProviderChange(p)}
                  className={`flex items-center gap-2.5 py-2.5 px-3.5 rounded-xl border text-sm font-medium transition-all ${
                    provider === p
                      ? "border-accent bg-accent/10 text-accent shadow-sm"
                      : "border-border text-secondary hover:border-accent/40 hover:text-primary"
                  }`}
                  data-testid={`provider-${p}`}
                >
                  <span>{PROVIDER_ICONS[p]}</span>
                  <span>{PROVIDER_LABELS[p]}</span>
                </button>
              ))}
            </div>
          </div>

          {/* model */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-muted mb-2.5">
              Model
            </label>
            <div className="relative">
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full appearance-none bg-input border border-border rounded-xl px-4 py-2.5 text-sm text-primary focus:outline-none focus:border-accent cursor-pointer pr-8"
                data-testid="model-select"
              >
                {options.map((m) => (
                  <option key={m.value} value={m.value} className="bg-elevated">
                    {m.label}
                  </option>
                ))}
              </select>
              <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                  <path d="M6 8L1 3h10z" />
                </svg>
              </div>
            </div>
          </div>

          {/* create button */}
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !model}
            className="w-full py-2.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold rounded-xl transition-colors shadow-lg shadow-accent/20 mt-1"
            data-testid="create-chat-button"
          >
            {mutation.isPending ? "Creating…" : "Start Chat"}
          </button>

          {mutation.isError && (
            <p className="text-sm text-red-400 text-center">
              {mutation.error instanceof Error ? mutation.error.message : "Failed to create chat"}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
