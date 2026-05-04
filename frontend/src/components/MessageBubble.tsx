import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";
import {
  XIcon, ChevronDownIcon, ChevronRightIcon,
  CheckIcon, LoaderIcon, GlobeIcon, ImageIcon, CopyIcon, AlertCircleIcon,
} from "lucide-react";
import type { Message, InlineImage, ToolCallRecord } from "../types";
import { getToken } from "../lib/api";
import SvgCanvas from "./SvgCanvas";

interface Props {
  message: Message;
  images?: InlineImage[];
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
    if (!url.startsWith("/api/generated/") || !token) {
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
      className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4"
      onClick={onClose}
      data-testid="image-lightbox"
    >
      <div className="relative" onClick={(e) => e.stopPropagation()}>
        <button
          className="absolute -top-4 -right-4 w-8 h-8 rounded-full bg-white/20 hover:bg-white/40 text-white flex items-center justify-center z-10 transition-colors"
          onClick={onClose}
          data-testid="image-lightbox-close"
        >
          <XIcon size={16} />
        </button>
        <img
          src={src}
          alt={img.prompt}
          className="max-w-[90vw] max-h-[90vh] object-contain rounded-xl"
        />
        {img.prompt && (
          <p className="text-xs text-white/60 mt-2 text-center">{img.prompt}</p>
        )}
      </div>
    </div>,
    document.body,
  );
}

function ImageThumbnail({ img, onClick }: { img: InlineImage; onClick: () => void }) {
  const src = useAuthedBlobUrl(img.url);
  return (
    <div className="mt-4">
      <img
        src={src}
        alt={img.prompt}
        className="rounded-xl max-w-sm max-h-80 object-contain border border-border cursor-pointer hover:opacity-90 transition-opacity"
        loading="lazy"
        onClick={onClick}
        data-testid="generated-image"
      />
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

export default function MessageBubble({ message, images = message.images ?? [] }: Props) {
  const isUser = message.role === "user";

  return (
    <div className="group flex gap-3 max-w-3xl w-full mx-auto animate-fade-in" data-testid={`message-${message.role}`}>
      <Avatar role={message.role} />
      <div className="flex-1 min-w-0 pt-0.5">
        <p className="text-xs font-semibold text-muted mb-1.5">
          {isUser ? "You" : "Assistant"}
        </p>
        {!isUser && message.thinking && <ThinkingBubble content={message.thinking} />}
        {isUser ? (
          <p className="text-[0.9375rem] text-primary leading-[1.7] whitespace-pre-wrap">
            {message.content}
          </p>
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

export function StreamingBubble({ content, images }: { content: string; images: InlineImage[] }) {
  return (
    <div className="flex gap-3 max-w-3xl w-full mx-auto animate-fade-in">
      <Avatar role="assistant" />
      <div className="flex-1 min-w-0 pt-0.5">
        <p className="text-xs font-semibold text-muted mb-1.5">Assistant</p>
        <div className="prose-chat">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
            components={markdownComponents}
          >
            {content || "​"}
          </ReactMarkdown>
          <span className="cursor-blink" />
        </div>
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

export function ThinkingBubble({ content }: { content: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex gap-3 max-w-3xl w-full mx-auto" data-testid="thinking-bubble">
      <div className="w-7 h-7 flex-shrink-0" />
      <div className="border border-border/50 rounded-xl bg-elevated/50 text-xs text-muted overflow-hidden">
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
    </div>
  );
}

export function ToolCallsBubble({ calls }: { calls: ToolCallRecord[] }) {
  return (
    <div className="flex gap-3 max-w-3xl w-full mx-auto" data-testid="tool-calls-bubble">
      <div className="w-7 h-7 flex-shrink-0" />
      <div className="flex flex-col gap-1">
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
            <span>{TOOL_LABELS[call.name] ?? call.name}</span>
            {call.error ? (
              <AlertCircleIcon size={11} className="ml-auto" />
            ) : call.done ? (
              <CheckIcon size={11} className="ml-auto text-muted" />
            ) : (
              <LoaderIcon size={11} className="ml-auto animate-spin" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
