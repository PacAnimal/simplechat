import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";
import { XIcon, ChevronDownIcon, ChevronRightIcon, CheckIcon, LoaderIcon, GlobeIcon, ImageIcon } from "lucide-react";
import type { Message, InlineImage, ToolCallRecord } from "../types";

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

function Lightbox({ img, onClose }: { img: InlineImage; onClose: () => void }) {
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
          src={img.url}
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

function ImageGrid({ images }: { images: InlineImage[] }) {
  const [lightbox, setLightbox] = useState<InlineImage | null>(null);
  return (
    <>
      {images.map((img, i) => (
        <div key={i} className="mt-4">
          <img
            src={img.url}
            alt={img.prompt}
            className="rounded-xl max-w-sm max-h-80 object-contain border border-border cursor-pointer hover:opacity-90 transition-opacity"
            loading="lazy"
            onClick={() => setLightbox(img)}
            data-testid="generated-image"
          />
          <p className="text-xs text-muted mt-1.5 italic">{img.prompt}</p>
        </div>
      ))}
      {lightbox && <Lightbox img={lightbox} onClose={() => setLightbox(null)} />}
    </>
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
        {isUser ? (
          <p className="text-[0.9375rem] text-primary leading-[1.7] whitespace-pre-wrap">
            {message.content}
          </p>
        ) : (
          <div className="prose-chat">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
              {message.content}
            </ReactMarkdown>
          </div>
        )}
        <ImageGrid images={images} />
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
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
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
              call.done
                ? "border-border/40 text-muted bg-elevated/30"
                : "border-accent/30 text-accent bg-accent/5"
            }`}
          >
            <ToolIcon name={call.name} />
            <span>{TOOL_LABELS[call.name] ?? call.name}</span>
            {call.done ? (
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
