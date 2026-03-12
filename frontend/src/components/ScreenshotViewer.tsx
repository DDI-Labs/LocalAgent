import { useRef, useState, useEffect } from "react";
import { Monitor, ZoomIn, ZoomOut, Crosshair } from "lucide-react";
import type { ScreenshotData } from "@/hooks/useAgentSocket";

interface ScreenshotViewerProps {
  data: ScreenshotData | null;
}

export function ScreenshotViewer({ data }: ScreenshotViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [imgNatural, setImgNatural] = useState({ w: 1, h: 1 });
  const [zoom, setZoom] = useState(false);

  // Track the natural size of the image so we can compute the click dot position
  useEffect(() => {
    if (!imgRef.current) return;
    const img = imgRef.current;
    const update = () => {
      if (img.naturalWidth > 0) {
        setImgNatural({ w: img.naturalWidth, h: img.naturalHeight });
      }
    };
    img.addEventListener("load", update);
    update();
    return () => img.removeEventListener("load", update);
  }, [data?.image]);

  if (!data) {
    return (
      <div className="flex flex-col rounded-xl border border-border bg-bg-card">
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <Monitor className="h-4 w-4 text-accent" />
          <span className="text-sm font-semibold tracking-wide text-text-secondary uppercase">
            Screen View
          </span>
        </div>
        <div className="flex h-64 items-center justify-center bg-terminal-bg text-text-secondary text-sm">
          No screenshot yet — run a task to see the agent's view
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col rounded-xl border border-border bg-bg-card">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <Monitor className="h-4 w-4 text-accent" />
          <span className="text-sm font-semibold tracking-wide text-text-secondary uppercase">
            Screen View
          </span>
          <span className="rounded-full bg-bg-secondary px-2 py-0.5 text-xs text-text-secondary">
            {data.timestamp}
          </span>
          {data.click && (
            <span className="flex items-center gap-1 rounded-full bg-danger/15 px-2 py-0.5 text-xs text-danger">
              <Crosshair className="h-3 w-3" />
              ({data.click.x}, {data.click.y})
            </span>
          )}
        </div>
        <button
          onClick={() => setZoom((z) => !z)}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-text-secondary transition-colors hover:bg-bg-secondary hover:text-text-primary"
        >
          {zoom ? <ZoomOut className="h-3 w-3" /> : <ZoomIn className="h-3 w-3" />}
          {zoom ? "Fit" : "Zoom"}
        </button>
      </div>

      {/* Screenshot with click overlay */}
      <div
        ref={containerRef}
        className="terminal-scroll relative overflow-auto bg-terminal-bg"
        style={{ maxHeight: zoom ? "600px" : "384px" }}
      >
        <div className="relative inline-block w-full">
          <img
            ref={imgRef}
            src={data.image}
            alt="Agent screenshot"
            className={zoom ? "w-auto max-w-none" : "w-full"}
            draggable={false}
          />

          {/* Click dot overlay — positioned as a percentage of the image */}
          {data.click && imgNatural.w > 1 && (
            <div
              className="pointer-events-none absolute"
              style={{
                left: `${(data.click.x / imgNatural.w) * 100}%`,
                top: `${(data.click.y / imgNatural.h) * 100}%`,
                transform: "translate(-50%, -50%)",
              }}
            >
              {/* Outer pulse ring */}
              <div className="absolute -inset-3 animate-ping rounded-full border-2 border-danger opacity-40" />
              {/* Inner dot */}
              <div className="h-3 w-3 rounded-full border-2 border-white bg-danger shadow-lg shadow-danger/50" />
              {/* Crosshair lines */}
              <div className="absolute left-1/2 top-1/2 h-6 w-px -translate-x-1/2 -translate-y-1/2 bg-danger/60" />
              <div className="absolute left-1/2 top-1/2 h-px w-6 -translate-x-1/2 -translate-y-1/2 bg-danger/60" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
