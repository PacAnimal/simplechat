import { useEffect, useLayoutEffect, useRef, useState, useCallback } from "react";
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
  provider?: string;
}

export default function MessageInput({
  onSend,
  onUploadFile,
  webSearchEnabled,
  onToggleWebSearch,
  disabled,
  initialValue,
  provider,
}: Props) {
  const [text, setText] = useState(initialValue ?? "");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [previews, setPreviews] = useState<Map<number, string>>(new Map());
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingCursorRef = useRef<number | null>(null);

  const attachmentsDisabled = provider === "ollama";

  useLayoutEffect(() => {
    if (pendingCursorRef.current !== null && textareaRef.current) {
      const pos = pendingCursorRef.current;
      pendingCursorRef.current = null;
      textareaRef.current.selectionStart = pos;
      textareaRef.current.selectionEnd = pos;
      const el = textareaRef.current;
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
    }
  });

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

  function revokePreview(id: number) {
    const url = previews.get(id);
    if (url) {
      URL.revokeObjectURL(url);
      setPreviews((prev) => { const m = new Map(prev); m.delete(id); return m; });
    }
  }

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if ((!trimmed && attachments.length === 0) || disabled) return;
    onSend(trimmed, attachments.map((a) => a.id));
    setText("");
    setAttachments([]);
    previews.forEach((url) => URL.revokeObjectURL(url));
    setPreviews(new Map());
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.focus();
    }
  }, [text, attachments, previews, disabled, onSend]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey) {
      e.preventDefault();
      handleSend();
      return;
    }
    if (e.key === "Enter" && (e.shiftKey || e.ctrlKey)) {
      e.preventDefault();
      const el = e.currentTarget;
      const start = el.selectionStart ?? text.length;
      const end = el.selectionEnd ?? text.length;
      pendingCursorRef.current = start + 1;
      setText(text.slice(0, start) + "\n" + text.slice(end));
    }
  }

  function handleTextChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setText(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }

  async function handleFiles(files: File[]) {
    if (attachmentsDisabled || files.length === 0) return;
    setUploadError(null);
    for (const rawFile of files) {
      // give nameless clipboard files a sensible filename
      const name =
        rawFile.name ||
        (rawFile.type.startsWith("image/")
          ? `screenshot-${Date.now()}.${rawFile.type.split("/")[1] || "png"}`
          : `pasted-${Date.now()}`);
      const file = rawFile.name ? rawFile : new File([rawFile], name, { type: rawFile.type });
      const previewUrl = file.type.startsWith("image/") ? URL.createObjectURL(file) : null;
      setUploading(true);
      try {
        const att = await onUploadFile(file);
        setAttachments((prev) => [...prev, att]);
        if (previewUrl) setPreviews((prev) => new Map(prev).set(att.id, previewUrl));
      } catch (err) {
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        const msg = err instanceof Error ? err.message : String(err);
        const body = msg.includes(": ") ? msg.split(": ").slice(1).join(": ") : msg;
        setUploadError(body);
      } finally {
        setUploading(false);
      }
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    handleFiles(files);
  }

  function handlePaste(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    if (attachmentsDisabled) return;
    const files = Array.from(e.clipboardData.files);
    if (files.length > 0) {
      e.preventDefault();
      handleFiles(files);
      return;
    }
    // macOS screenshots land in items, not files
    const imageFiles = Array.from(e.clipboardData.items)
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .map((item) => item.getAsFile())
      .filter((f): f is File => f !== null);
    if (imageFiles.length > 0) {
      e.preventDefault();
      handleFiles(imageFiles);
    }
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    if (attachmentsDisabled) return;
    e.preventDefault();
    setIsDragOver(true);
  }

  function handleDragLeave(e: React.DragEvent<HTMLDivElement>) {
    // only clear if leaving the container entirely
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragOver(false);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
    if (attachmentsDisabled) return;
    const files = Array.from(e.dataTransfer.files);
    handleFiles(files);
  }

  const canSend = (!!text.trim() || attachments.length > 0) && !disabled;

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
            {attachments.map((att) => {
              const preview = previews.get(att.id);
              const isImage = att.mime_type.startsWith("image/");
              return (
                <div
                  key={att.id}
                  className={cn(
                    "flex items-center gap-1.5 bg-elevated border border-border rounded-lg text-xs text-secondary overflow-hidden",
                    isImage && preview ? "" : "px-3 py-1.5",
                  )}
                  data-testid="attachment-chip"
                >
                  {isImage && preview ? (
                    <>
                      <img src={preview} alt="" className="h-9 w-9 object-cover flex-shrink-0" />
                      <span className="truncate max-w-28 py-1.5">{att.filename}</span>
                      <span className="text-muted">({formatBytes(att.size)})</span>
                      <button
                        onClick={() => { revokePreview(att.id); setAttachments((p) => p.filter((a) => a.id !== att.id)); }}
                        className="text-muted hover:text-primary ml-0.5 mr-2"
                      >
                        <XIcon size={11} />
                      </button>
                    </>
                  ) : (
                    <>
                      <PaperclipIcon size={11} />
                      <span className="truncate max-w-36">{att.filename}</span>
                      <span className="text-muted">({formatBytes(att.size)})</span>
                      <button
                        onClick={() => setAttachments((p) => p.filter((a) => a.id !== att.id))}
                        className="text-muted hover:text-primary ml-0.5"
                      >
                        <XIcon size={11} />
                      </button>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* main input container */}
        <div
          className={cn(
            "flex flex-col bg-input border border-border rounded-2xl shadow-lg overflow-hidden focus-within:border-accent/60 transition-colors",
            isDragOver && !attachmentsDisabled && "border-accent/60 bg-accent/5",
          )}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleTextChange}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder="Message SimpleChat…"
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
                disabled={uploading || disabled || attachmentsDisabled}
                title={attachmentsDisabled ? "Attachments not supported for Ollama" : "Attach file"}
                className="p-1.5 rounded-lg text-muted hover:text-secondary hover:bg-hover disabled:opacity-40 transition-colors"
                data-testid="attach-button"
              >
                <PaperclipIcon size={16} />
              </button>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={handleFileChange}
                accept=".txt,.md,.csv,.json,.pdf,.xls,.xlsx,.docx,.pptx,.png,.jpg,.jpeg,.gif,.webp,.bmp"
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

        <p className="hidden wide:block text-center text-[0.7rem] text-muted mt-2">
          Enter to send · Shift+Enter or Ctrl+Enter for newline
        </p>
      </div>
    </div>
  );
}
