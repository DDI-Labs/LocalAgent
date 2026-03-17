import { useRef, useState, useEffect, useCallback } from "react";
import { Monitor, ZoomIn, ZoomOut, Crosshair, MousePointerClick, Target, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ScreenshotData } from "@/hooks/useAgentSocket";

interface ScreenshotViewerProps {
  data: ScreenshotData | null;
  /** When true the image is clickable (HITL takeover or correction mode). */
  takeoverMode?: boolean;
  /** When true the image is clickable for teach-mode step recording. */
  teachMode?: boolean;
  /** Called with (x, y) in natural image coordinates when the user clicks in takeover mode. */
  onTakeoverClick?: (x: number, y: number) => void;
  /** Called with (x, y) in natural image coordinates when the user clicks in teach mode. */
  onTeachClick?: (x: number, y: number) => void;
  /** Proposed click from the agent (training mode) — shown as an accent-colored dot. */
  proposedClick?: { x: number; y: number };
}

export function ScreenshotViewer({
  data,
  takeoverMode = false,
  teachMode = false,
  onTakeoverClick,
  onTeachClick,
  proposedClick,
}: ScreenshotViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [imgNatural, setImgNatural] = useState({ w: 1, h: 1 });
  const [zoom, setZoom] = useState(false);
  const [hoverCoords, setHoverCoords] = useState<{ x: number; y: number } | null>(null);

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

  /** Convert a mouse event on the image to natural image coordinates. */
  const toNaturalCoords = useCallback(
    (e: React.MouseEvent<HTMLImageElement>) => {
      const img = imgRef.current;
      if (!img) return null;
      const rect = img.getBoundingClientRect();
      const scaleX = img.naturalWidth / rect.width;
      const scaleY = img.naturalHeight / rect.height;
      return {
        x: Math.round((e.clientX - rect.left) * scaleX),
        y: Math.round((e.clientY - rect.top) * scaleY),
      };
    },
    [],
  );

  const isClickable = takeoverMode || teachMode;

  const handleImageClick = useCallback(
    (e: React.MouseEvent<HTMLImageElement>) => {
      const coords = toNaturalCoords(e);
      if (!coords) return;
      if (takeoverMode && onTakeoverClick) {
        onTakeoverClick(coords.x, coords.y);
      } else if (teachMode && onTeachClick) {
        onTeachClick(coords.x, coords.y);
      }
    },
    [takeoverMode, teachMode, onTakeoverClick, onTeachClick, toNaturalCoords],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLImageElement>) => {
      if (!isClickable) return;
      const coords = toNaturalCoords(e);
      setHoverCoords(coords);
    },
    [isClickable, toNaturalCoords],
  );

  const handleMouseLeave = useCallback(() => setHoverCoords(null), []);

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
    <div
      className={cn(
        "flex flex-col rounded-xl border bg-bg-card",
        takeoverMode
          ? "border-2 border-warning/60 shadow-lg shadow-warning/10"
          : teachMode
            ? "border-2 border-success/60 shadow-lg shadow-success/10"
            : "border-border",
      )}
    >
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
          {teachMode && (
            <span className="flex items-center gap-1 rounded-full bg-success/20 px-2 py-0.5 text-xs font-medium text-success">
              <BookOpen className="h-3 w-3" />
              Click to record step
            </span>
          )}
          {takeoverMode && (
            <span className="flex animate-pulse-dot items-center gap-1 rounded-full bg-warning/20 px-2 py-0.5 text-xs font-medium text-warning">
              <MousePointerClick className="h-3 w-3" />
              Click to help
            </span>
          )}
          {!takeoverMode && data.click && (
            <span className="flex items-center gap-1 rounded-full bg-danger/15 px-2 py-0.5 text-xs text-danger">
              <Crosshair className="h-3 w-3" />
              ({data.click.x}, {data.click.y})
            </span>
          )}
          {proposedClick && (
            <span className="flex items-center gap-1 rounded-full bg-accent/15 px-2 py-0.5 text-xs text-accent">
              <Target className="h-3 w-3" />
              Proposed ({proposedClick.x}, {proposedClick.y})
            </span>
          )}
          {isClickable && hoverCoords && (
            <span className="font-mono text-xs text-text-secondary">
              ({hoverCoords.x}, {hoverCoords.y})
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
            className={cn(
              zoom ? "w-auto max-w-none" : "w-full",
              isClickable && "cursor-crosshair",
            )}
            draggable={false}
            onClick={handleImageClick}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
          />

          {/* Click dot overlay — positioned as a percentage of the image */}
          {!takeoverMode && data.click && imgNatural.w > 1 && (
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

          {/* Proposed click dot (training mode) — accent-colored */}
          {proposedClick && imgNatural.w > 1 && (
            <div
              className="pointer-events-none absolute"
              style={{
                left: `${(proposedClick.x / imgNatural.w) * 100}%`,
                top: `${(proposedClick.y / imgNatural.h) * 100}%`,
                transform: "translate(-50%, -50%)",
              }}
            >
              {/* Outer pulse ring */}
              <div className="absolute -inset-3 animate-ping rounded-full border-2 border-accent opacity-40" />
              {/* Inner dot */}
              <div className="h-3 w-3 rounded-full border-2 border-white bg-accent shadow-lg shadow-accent/50" />
              {/* Crosshair lines */}
              <div className="absolute left-1/2 top-1/2 h-6 w-px -translate-x-1/2 -translate-y-1/2 bg-accent/60" />
              <div className="absolute left-1/2 top-1/2 h-px w-6 -translate-x-1/2 -translate-y-1/2 bg-accent/60" />
            </div>
          )}

          {/* Interactive hover crosshair (takeover or teach) */}
          {isClickable && hoverCoords && imgNatural.w > 1 && (
            <div
              className="pointer-events-none absolute"
              style={{
                left: `${(hoverCoords.x / imgNatural.w) * 100}%`,
                top: `${(hoverCoords.y / imgNatural.h) * 100}%`,
                transform: "translate(-50%, -50%)",
              }}
            >
              <div className={cn(
                "h-4 w-4 rounded-full border-2 shadow-lg",
                teachMode
                  ? "border-success bg-success/30 shadow-success/50"
                  : "border-warning bg-warning/30 shadow-warning/50",
              )} />
              <div className={cn(
                "absolute left-1/2 top-1/2 h-8 w-px -translate-x-1/2 -translate-y-1/2",
                teachMode ? "bg-success/60" : "bg-warning/60",
              )} />
              <div className={cn(
                "absolute left-1/2 top-1/2 h-px w-8 -translate-x-1/2 -translate-y-1/2",
                teachMode ? "bg-success/60" : "bg-warning/60",
              )} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
