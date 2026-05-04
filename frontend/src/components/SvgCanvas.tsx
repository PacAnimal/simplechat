import { useEffect, useState } from "react";
import { CheckIcon, CopyIcon } from "lucide-react";

function sanitizeSvg(svg: string): string {
  return svg
    .replace(/<script\b[\s\S]*?<\/script>/gi, "")
    .replace(/\s+on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]*)/gi, "")
    .replace(/\bhref\s*=\s*"javascript:[^"]*"/gi, 'href="#"')
    .replace(/\bhref\s*=\s*'javascript:[^']*'/gi, "href='#'");
}

export default function SvgCanvas({ svg }: { svg: string }) {
  const [darkBg, setDarkBg] = useState(false);
  const [copied, setCopied] = useState(false);
  const clean = sanitizeSvg(svg);

  useEffect(() => {
    const blob = new Blob([clean], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      const W = img.naturalWidth || 512;
      const H = img.naturalHeight || 512;
      const canvas = document.createElement("canvas");
      canvas.width = W;
      canvas.height = H;
      const ctx = canvas.getContext("2d");
      if (!ctx) { URL.revokeObjectURL(url); return; }
      ctx.drawImage(img, 0, 0);
      try {
        const { data } = ctx.getImageData(0, 0, W, H);
        let grey = 0, total = 0;
        for (let i = 0; i < data.length; i += 4) {
          if (data[i + 3] < 16) continue; // skip transparent
          total++;
          const r = data[i], g = data[i + 1], b = data[i + 2];
          // mid-range grey: low saturation, not near black or white
          if (Math.max(r, g, b) - Math.min(r, g, b) < 30 && r > 100 && r < 210) grey++;
        }
        if (total > 0 && grey / total > 0.35) setDarkBg(true);
      } catch { /* tainted canvas — skip detection */ }
      URL.revokeObjectURL(url);
    };
    img.onerror = () => URL.revokeObjectURL(url);
    img.src = url;
  }, [clean]);

  async function copySvg(e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(svg);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard unavailable */ }
  }

  return (
    <div
      className={`relative group rounded-xl p-4 my-3 flex items-center justify-center overflow-hidden transition-colors ${
        darkBg ? "bg-black" : "bg-neutral-500/25"
      }`}
    >
      <div
        className="max-w-full [&>svg]:max-w-full [&>svg]:h-auto"
        dangerouslySetInnerHTML={{ __html: clean }}
      />
      <button
        onClick={copySvg}
        className="absolute top-2 right-2 p-1.5 rounded-md bg-black/50 hover:bg-black/70 text-white/80 hover:text-white transition-colors opacity-0 group-hover:opacity-100"
        title="Copy SVG"
      >
        {copied ? <CheckIcon size={12} /> : <CopyIcon size={12} />}
      </button>
    </div>
  );
}
