import { useEffect, useRef, useState, useCallback } from "react";
import { ArrowUpIcon, PaperclipIcon, GlobeIcon, XIcon } from "lucide-react";
import { cn } from "../lib/utils";
import { formatBytes } from "../lib/utils";
import type { Attachment } from "../types";

interface Props {
  onSend: (content: string, attachmentIds: number[]) => void;
  onUploadFile: (file: File) => Promise<Attachment>;
  webSearchEnabled: boolean;
  onToggleWebSearch: () => void;
  disabled?: boolean;
  initialValue?: string;
}

export default function MessageInput({
  onSend,
  onUploadFile,
  webSearchEnabled,
  onToggleWebSearch,
  disabled,
  initialValue,
}: Props) {
  const [text, setText] = useState(initialValue ?? "");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // sync initial value when it first arrives (suggestion card path)
  useEffect(() => {
    if (initialValue) {
      setText(initialValue); // eslint-disable-line react-hooks/set-state-in-effect
      if (textareaRef.current) {
        const el = textareaRef.current;
        el.style.height = "auto";
        el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
        el.focus();
      }
    }
  }, [initialValue]);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, attachments.map((a) => a.id));
    setText("");
    setAttachments([]);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }, [text, attachments, disabled, onSend]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleTextChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setText(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setUploadError(null);
    setUploading(true);
    try {
      const att = await onUploadFile(file);
      setAttachments((prev) => [...prev, att]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      // extract user-friendly message from "415: Unsupported file type..."
      const body = msg.includes(": ") ? msg.split(": ").slice(1).join(": ") : msg;
      setUploadError(body);
    } finally {
      setUploading(false);
    }
  }

  const canSend = !!text.trim() && !disabled;

  return (
    <div className="pb-6 px-4">
      <div className="max-w-3xl mx-auto">
        {/* upload error */}
        {uploadError && (
          <div className="flex items-center gap-2 text-xs text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2 mb-2">
            <span className="flex-1">{uploadError}</span>
            <button onClick={() => setUploadError(null)} className="text-muted hover:text-primary flex-shrink-0">
              <XIcon size={11} />
            </button>
          </div>
        )}

        {/* attachment pills */}
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2 px-1">
            {attachments.map((att) => (
              <div
                key={att.id}
                className="flex items-center gap-1.5 bg-elevated border border-border rounded-lg px-3 py-1.5 text-xs text-secondary"
                data-testid="attachment-chip"
              >
                <PaperclipIcon size={11} />
                <span className="truncate max-w-36">{att.filename}</span>
                <span className="text-muted">({formatBytes(att.size)})</span>
                <button
                  onClick={() => setAttachments((p) => p.filter((a) => a.id !== att.id))}
                  className="text-muted hover:text-primary ml-0.5"
                >
                  <XIcon size={11} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* main input container */}
        <div className="flex flex-col bg-input border border-border rounded-2xl shadow-lg overflow-hidden focus-within:border-accent/60 transition-colors">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleTextChange}
            onKeyDown={handleKeyDown}
            placeholder="Message SimpleChat…"
            disabled={disabled}
            rows={1}
            className="w-full bg-transparent text-[0.9375rem] text-primary placeholder-muted resize-none outline-none px-4 pt-3.5 pb-2 max-h-60 leading-relaxed font-sans"
            data-testid="message-input"
          />

          {/* toolbar row */}
          <div className="flex items-center justify-between px-3 pb-3 pt-1">
            <div className="flex items-center gap-1">
              {/* file attach */}
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading || disabled}
                className="p-1.5 rounded-lg text-muted hover:text-secondary hover:bg-hover disabled:opacity-40 transition-colors"
                title="Attach file"
                data-testid="attach-button"
              >
                <PaperclipIcon size={16} />
              </button>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={handleFileChange}
                accept=".txt,.md,.csv,.json,text/plain,text/markdown,text/csv,application/json"
              />

              {/* web search */}
              <button
                type="button"
                onClick={onToggleWebSearch}
                className={cn(
                  "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors",
                  webSearchEnabled
                    ? "bg-accent/15 text-accent border border-accent/30"
                    : "text-muted hover:text-secondary hover:bg-hover",
                )}
                title="Toggle web search"
                data-testid="web-search-toggle"
              >
                <GlobeIcon size={14} />
                {webSearchEnabled && <span>Search</span>}
              </button>
            </div>

            {/* send button */}
            <button
              type="button"
              onClick={handleSend}
              disabled={!canSend}
              className={cn(
                "w-8 h-8 rounded-full flex items-center justify-center transition-all",
                canSend
                  ? "bg-accent hover:bg-accent-hover text-white shadow-md shadow-accent/30"
                  : "bg-elevated text-muted cursor-not-allowed",
              )}
              data-testid="send-button"
            >
              <ArrowUpIcon size={15} strokeWidth={2.5} />
            </button>
          </div>
        </div>

        <p className="text-center text-[0.7rem] text-muted mt-2">
          Enter to send · Shift+Enter for newline
        </p>
      </div>
    </div>
  );
}
