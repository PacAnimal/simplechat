import React, { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";
import {
  XIcon, ChevronDownIcon, ChevronRightIcon,
  CheckIcon, LoaderIcon, GlobeIcon, ImageIcon, CopyIcon, AlertCircleIcon,
  PaperclipIcon, DownloadIcon,
} from "lucide-react";
import type { Message, InlineImage, ToolCallRecord, Attachment } from "../types";
import { getToken } from "../lib/api";
import { formatBytes } from "../lib/utils";
import SvgCanvas from "./SvgCanvas";

interface Props {
  message: Message;
  images?: InlineImage[];
  noAnimate?: boolean;
}

function Avatar({ role }: { role: string }) {
  if (role === "user") {
    return (
      <div className="w-7 h-7 rounded-full bg-accent/20 flex items-center justify-center flex-shrink-0 text-xs font-semibold text-accent">
        U
      </div>
    );
  }
  return (
    <div className="w-7 h-7 rounded-full bg-elevated border border-border flex items-center justify-center flex-shrink-0">
      <span className="text-xs">✦</span>
    </div>
  );
}

function useAuthedBlobUrl(url: string): string {
  const [blobUrl, setBlobUrl] = useState("");
  useEffect(() => {
    const token = getToken();
    const needsAuth = url.startsWith("/api/generated/") || url.startsWith("/api/files/");
    if (!needsAuth || !token) {
      setBlobUrl(url);
      return;
    }
    let objectUrl = "";
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      })
      .catch(() => setBlobUrl(url));
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);
  return blobUrl;
}

async function downloadAttachment(att: Attachment) {
  const token = getToken();
  const url = `/api/files/${att.id}/download`;
  const resp = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!resp.ok) return;
  const blob = await resp.blob();
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objUrl;
  a.download = att.filename;
  a.click();
  URL.revokeObjectURL(objUrl);
}

function AttachedImageThumb({ att, onClick }: { att: Attachment; onClick: () => void }) {
  const src = useAuthedBlobUrl(`/api/files/${att.id}/download`);
  return (
    <div className="relative group/img inline-block">
      <img
        src={src}
        alt={att.filename}
        className="h-16 w-16 object-cover rounded-lg border border-border cursor-pointer hover:opacity-90 transition-opacity"
        onClick={onClick}
      />
    </div>
  );
}

function AttachmentStrip({ attachments }: { attachments: Attachment[] }) {
  const [lightbox, setLightbox] = useState<Attachment | null>(null);
  if (!attachments.length) return null;

  const images = attachments.filter((a) => a.mime_type.startsWith("image/"));
  const files = attachments.filter((a) => !a.mime_type.startsWith("image/"));

  return (
    <div className="flex flex-wrap gap-2 mt-2">
      {images.map((att) => (
        <AttachedImageThumb key={att.id} att={att} onClick={() => setLightbox(att)} />
      ))}
      {files.map((att) => (
        <button
          key={att.id}
          onClick={() => downloadAttachment(att)}
          className="flex items-center gap-1.5 bg-elevated border border-border rounded-lg px-3 py-1.5 text-xs text-secondary hover:text-primary hover:border-accent/50 transition-colors"
          title={`Download ${att.filename}`}
        >
          <PaperclipIcon size={11} />
          <span className="truncate max-w-36">{att.filename}</span>
          <span className="text-muted">({formatBytes(att.size)})</span>
          <DownloadIcon size={10} className="ml-0.5 text-muted" />
        </button>
      ))}
      {lightbox && (
        <Lightbox
          img={{ url: `/api/files/${lightbox.id}/download`, prompt: lightbox.filename }}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}

function Lightbox({ img, onClose }: { img: InlineImage; onClose: () => void }) {
  const src = useAuthedBlobUrl(img.url);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-8"
      onClick={onClose}
      data-testid="image-lightbox"
    >
      <button
        className="absolute top-4 right-4 w-9 h-9 rounded-full bg-white/20 hover:bg-white/40 text-white flex items-center justify-center z-10 transition-colors"
        onClick={(e) => { e.stopPropagation(); onClose(); }}
        data-testid="image-lightbox-close"
      >
        <XIcon size={16} />
      </button>
      <div className="flex flex-col items-center">
        <img
          src={src}
          alt={img.prompt}
          className="max-w-[90vw] max-h-[85vh] object-contain rounded-xl block"
          onClick={(e) => e.stopPropagation()}
        />
        {img.prompt && (
          <p className="text-xs text-white/60 mt-2 text-center max-w-[90vw]">{img.prompt}</p>
        )}
      </div>
    </div>,
    document.body,
  );
}

function HoverCopyButton({ onCopy, className = "" }: { onCopy: () => void; className?: string }) {
  const [copied, setCopied] = useState(false);
  function handleClick(e: React.MouseEvent) {
    e.stopPropagation();
    onCopy();
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <button
      onClick={handleClick}
      className={`absolute top-2 right-2 p-1.5 rounded-md bg-black/50 hover:bg-black/70 text-white/80 hover:text-white transition-colors opacity-0 group-hover:opacity-100 ${className}`}
      title="Copy"
    >
      {copied ? <CheckIcon size={12} /> : <CopyIcon size={12} />}
    </button>
  );
}

function ImageThumbnail({ img, onClick }: { img: InlineImage; onClick: () => void }) {
  const src = useAuthedBlobUrl(img.url);

  async function copyImage() {
    try {
      const res = await fetch(src);
      const blob = await res.blob();
      await navigator.clipboard.write([new ClipboardItem({ [blob.type]: blob })]);
    } catch { /* clipboard unavailable */ }
  }

  return (
    <div className="mt-4 relative group inline-block">
      <img
        src={src}
        alt={img.prompt}
        className="rounded-xl max-w-sm max-h-80 object-contain border border-border cursor-pointer hover:opacity-90 transition-opacity"
        loading="lazy"
        onClick={onClick}
        data-testid="generated-image"
      />
      <HoverCopyButton onCopy={copyImage} />
      <p className="text-xs text-muted mt-1.5 italic">{img.prompt}</p>
    </div>
  );
}

function ImageGrid({ images }: { images: InlineImage[] }) {
  const [lightbox, setLightbox] = useState<InlineImage | null>(null);
  return (
    <>
      {images.map((img, i) => (
        <ImageThumbnail key={i} img={img} onClick={() => setLightbox(img)} />
      ))}
      {lightbox && <Lightbox img={lightbox} onClose={() => setLightbox(null)} />}
    </>
  );
}

function getNodeText(node: React.ReactNode): string {
  if (typeof node === "string") return node;
  if (typeof node === "number") return String(node);
  if (!node) return "";
  if (Array.isArray(node)) return node.map(getNodeText).join("");
  if (typeof node === "object" && "props" in (node as object)) {
    return getNodeText((node as React.ReactElement).props.children);
  }
  return "";
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard access denied or unavailable */ }
  }
  return (
    <button
      onClick={copy}
      className="absolute top-2 right-2 p-1.5 rounded-md bg-white/10 hover:bg-white/20 text-white/60 hover:text-white transition-colors opacity-0 group-hover/pre:opacity-100"
      title="Copy code"
    >
      {copied ? <CheckIcon size={12} /> : <CopyIcon size={12} />}
    </button>
  );
}

function MessageCopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard access denied or unavailable */ }
  }
  return (
    <button
      onClick={copy}
      className="flex items-center gap-1 p-1 rounded text-muted hover:text-primary transition-colors opacity-0 group-hover:opacity-100"
      title="Copy response"
    >
      {copied ? <CheckIcon size={13} /> : <CopyIcon size={13} />}
    </button>
  );
}

// split message content into text segments and raw <svg>...</svg> blocks
const CODE_FENCE_RE = /```[\s\S]*?```/g;
const RAW_SVG_RE = /<svg[\s\S]*?<\/svg>/gi;

type ContentPart = { type: "text"; value: string } | { type: "svg"; value: string };

function splitContent(content: string): ContentPart[] {
  const codeRanges: [number, number][] = [];
  for (const m of content.matchAll(CODE_FENCE_RE)) {
    codeRanges.push([m.index!, m.index! + m[0].length]);
  }
  const inCode = (i: number) => codeRanges.some(([s, e]) => i >= s && i < e);

  const parts: ContentPart[] = [];
  let lastIndex = 0;
  for (const m of content.matchAll(RAW_SVG_RE)) {
    if (inCode(m.index!)) continue;
    if (m.index! > lastIndex) parts.push({ type: "text", value: content.slice(lastIndex, m.index) });
    parts.push({ type: "svg", value: m[0] });
    lastIndex = m.index! + m[0].length;
  }
  if (lastIndex < content.length) parts.push({ type: "text", value: content.slice(lastIndex) });
  return parts.length ? parts : [{ type: "text", value: content }];
}

function isSvgCodeBlock(children: React.ReactNode): string | null {
  const child = Array.isArray(children) ? children[0] : children;
  if (!child || !React.isValidElement(child)) return null;
  const cls: string = (child.props as { className?: string }).className ?? "";
  const lang = /language-(\w+)/.exec(cls)?.[1] ?? "";
  if (lang !== "svg" && lang !== "xml") return null;
  const text = getNodeText(children);
  return text.trimStart().startsWith("<svg") ? text : null;
}

const markdownComponents = {
  pre: ({ children, ...props }: React.ComponentPropsWithoutRef<"pre">) => {
    const svgText = isSvgCodeBlock(children);
    if (svgText) return <SvgCanvas svg={svgText} />;
    const text = getNodeText(children);
    return (
      <div className="relative group/pre">
        <pre {...props}>{children}</pre>
        {text && <CopyButton text={text} />}
      </div>
    );
  },
};

function AssistantContent({ content }: { content: string }) {
  const parts = splitContent(content);
  return (
    <div className="prose-chat">
      {parts.map((part, i) =>
        part.type === "svg" ? (
          <SvgCanvas key={i} svg={part.value} />
        ) : (
          <ReactMarkdown
            key={i}
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
            components={markdownComponents}
          >
            {part.value}
          </ReactMarkdown>
        )
      )}
    </div>
  );
}

export default function MessageBubble({ message, images = message.images ?? [], noAnimate = false }: Props) {
  const isUser = message.role === "user";
  // once noAnimate is set, permanently suppress the animation for this element's lifetime
  // so it doesn't retrigger if the prop clears when the next stream completes
  const suppressAnim = useRef(noAnimate);
  if (noAnimate) suppressAnim.current = true;

  return (
    <div
      className="group flex gap-3 max-w-3xl w-full mx-auto animate-fade-in"
      style={suppressAnim.current ? { animation: "none" } : undefined}
      data-testid={`message-${message.role}`}
    >
      <Avatar role={message.role} />
      <div className="flex-1 min-w-0 pt-0.5">
        <p className="text-xs font-semibold text-muted mb-1.5">
          {isUser ? "You" : "Assistant"}
        </p>
        {!isUser && message.thinking && <ThinkingPanel content={message.thinking} />}
        {isUser ? (
          <>
            <p className="text-[0.9375rem] text-primary leading-[1.7] whitespace-pre-wrap">
              {message.content}
            </p>
            <AttachmentStrip attachments={message.attachments ?? []} />
          </>
        ) : (
          <AssistantContent content={message.content} />
        )}
        <ImageGrid images={images} />
        {!isUser && (
          <div className="mt-1">
            <MessageCopyButton text={message.content} />
          </div>
        )}
      </div>
    </div>
  );
}

export function StreamingBubble({
  content,
  images,
  thinking,
  toolCalls,
}: {
  content: string;
  images: InlineImage[];
  thinking?: string;
  toolCalls?: ToolCallRecord[];
}) {
  return (
    <div className="flex gap-3 max-w-3xl w-full mx-auto animate-fade-in">
      <Avatar role="assistant" />
      <div className="flex-1 min-w-0 pt-0.5">
        <p className="text-xs font-semibold text-muted mb-1.5">Assistant</p>
        {thinking && <ThinkingPanel content={thinking} />}
        {toolCalls && toolCalls.length > 0 && <ToolCallsPanel calls={toolCalls} />}
        {content ? (
          <div className="prose-chat">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight]}
              components={markdownComponents}
            >
              {content}
            </ReactMarkdown>
            <span className="cursor-blink" />
          </div>
        ) : (
          <p className="text-[0.9375rem] leading-[1.7]">
            <span className="cursor-blink" />
          </p>
        )}
        <ImageGrid images={images} />
      </div>
    </div>
  );
}

const TOOL_LABELS: Record<string, string> = {
  generate_image: "Generating image",
  web_search: "Searching the web",
};

function ToolIcon({ name }: { name: string }) {
  if (name === "generate_image") return <ImageIcon size={12} />;
  if (name === "web_search") return <GlobeIcon size={12} />;
  return null;
}

// inner panel variants — no outer flex/spacer, designed for use inside a bubble's content area

function ThinkingPanel({ content }: { content: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-border/50 rounded-xl bg-elevated/50 text-xs text-muted overflow-hidden mb-2" data-testid="thinking-bubble">
      <button
        className="flex items-center gap-1.5 px-3 py-2 w-full text-left hover:text-primary transition-colors"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? <ChevronDownIcon size={12} /> : <ChevronRightIcon size={12} />}
        <span className="font-medium">Thinking…</span>
      </button>
      {open && (
        <pre className="px-3 pb-3 whitespace-pre-wrap font-mono text-[0.7rem] leading-relaxed text-muted/80 max-h-48 overflow-y-auto">
          {content}
        </pre>
      )}
    </div>
  );
}

function sourceDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function ToolCallsPanel({ calls }: { calls: ToolCallRecord[] }) {
  return (
    <div className="flex flex-col gap-1 mb-2" data-testid="tool-calls-bubble">
      {calls.map((call, i) => (
        <div
          key={i}
          className={`flex items-center gap-2 text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
            call.error
              ? "border-red-400/30 text-red-400 bg-red-400/5"
              : call.done
              ? "border-border/40 text-muted bg-elevated/30"
              : "border-accent/30 text-accent bg-accent/5"
          }`}
        >
          <ToolIcon name={call.name} />
          <span className="shrink-0">{TOOL_LABELS[call.name] ?? call.name}</span>
          {call.done && call.sources && call.sources.length > 0 && (
            <div className="flex items-center gap-1.5 ml-1 flex-wrap">
              {call.sources.slice(0, 6).map((url, j) => {
                const domain = sourceDomain(url);
                return (
                  <a
                    key={j}
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-0.5 opacity-60 hover:opacity-100 transition-opacity"
                    data-testid="search-source-chip"
                  >
                    <img
                      src={`https://www.google.com/s2/favicons?domain=${domain}&sz=16`}
                      alt=""
                      className="w-3 h-3 rounded-sm"
                    />
                    <span className="text-[0.65rem]">{domain}</span>
                  </a>
                );
              })}
            </div>
          )}
          {call.error ? (
            <AlertCircleIcon size={11} className="ml-auto shrink-0" />
          ) : call.done ? (
            <CheckIcon size={11} className="ml-auto shrink-0 text-muted" />
          ) : (
            <LoaderIcon size={11} className="ml-auto shrink-0 animate-spin" />
          )}
        </div>
      ))}
    </div>
  );
}

// kept for API compatibility — now delegates to the inner panel variants
export function ThinkingBubble({ content }: { content: string }) {
  return (
    <div className="flex gap-3 max-w-3xl w-full mx-auto" data-testid="thinking-bubble">
      <div className="w-7 h-7 flex-shrink-0" />
      <ThinkingPanel content={content} />
    </div>
  );
}

export function ToolCallsBubble({ calls }: { calls: ToolCallRecord[] }) {
  return (
    <div className="flex gap-3 max-w-3xl w-full mx-auto" data-testid="tool-calls-bubble">
      <div className="w-7 h-7 flex-shrink-0" />
      <ToolCallsPanel calls={calls} />
    </div>
  );
}
