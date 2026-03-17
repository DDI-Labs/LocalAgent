import { useState } from "react";
import {
  Camera,
  MousePointerClick,
  Type,
  Keyboard,
  Timer,
  CheckCircle2,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { TeachStep } from "@/hooks/useAgentSocket";

const COMMON_KEYS = [
  { label: "Enter", keys: ["Return"] },
  { label: "Tab", keys: ["Tab"] },
  { label: "Escape", keys: ["Escape"] },
  { label: "Backspace", keys: ["Backspace"] },
  { label: "Cmd+A", keys: ["cmd", "a"] },
  { label: "Cmd+C", keys: ["cmd", "c"] },
  { label: "Cmd+V", keys: ["cmd", "v"] },
  { label: "Cmd+Space", keys: ["cmd", "space"] },
  { label: "Cmd+T", keys: ["cmd", "t"] },
  { label: "Cmd+L", keys: ["cmd", "l"] },
];

interface TeachBarProps {
  steps: TeachStep[];
  hasScreenshot: boolean;
  onScreenshot: () => void;
  onType: (text: string) => void;
  onKeypress: (keys: string[]) => void;
  onWait: () => void;
  onDone: () => void;
  onCancel: () => void;
}

export function TeachBar({
  steps,
  hasScreenshot,
  onScreenshot,
  onType,
  onKeypress,
  onWait,
  onDone,
  onCancel,
}: TeachBarProps) {
  const [typeText, setTypeText] = useState("");

  const handleType = () => {
    if (!typeText.trim()) return;
    onType(typeText);
    setTypeText("");
  };

  // Before first screenshot: show a simple prompt to take one
  if (!hasScreenshot) {
    return (
      <div className="rounded-xl border-2 border-success/40 bg-bg-card p-5">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="rounded-lg bg-success/15 p-3">
            <Camera className="h-6 w-6 text-success" />
          </div>
          <div>
            <p className="text-sm font-medium text-text-primary">
              Arrange your screen for the starting point
            </p>
            <p className="mt-1 text-xs text-text-secondary">
              Navigate to the app or screen where the task begins, then capture a screenshot.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onCancel}
              className="flex items-center gap-1 rounded-lg border border-border px-4 py-2 text-sm text-text-secondary transition-colors hover:bg-bg-secondary hover:text-text-primary"
            >
              <X className="h-3.5 w-3.5" />
              Cancel
            </button>
            <button
              onClick={onScreenshot}
              className="flex items-center gap-1.5 rounded-lg border border-success/30 bg-success/10 px-5 py-2 text-sm font-medium text-success transition-colors hover:border-success hover:bg-success/20"
            >
              <Camera className="h-4 w-4" />
              Take Screenshot
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border-2 border-success/40 bg-bg-card">
      {/* Step list */}
      {steps.length > 0 && (
        <div className="max-h-40 overflow-y-auto border-b border-border px-4 py-3">
          <div className="mb-2 text-xs font-semibold tracking-wide text-text-secondary uppercase">
            Recorded Steps ({steps.length})
          </div>
          <div className="space-y-1.5">
            {steps.map((step, i) => (
              <div
                key={i}
                className="flex items-center gap-2 text-xs text-text-secondary"
              >
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-success/15 text-[10px] font-bold text-success">
                  {i + 1}
                </span>
                <StepIcon type={step.type} />
                <span className="text-text-primary">{describeStep(step)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action row */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-3">
        {/* Screenshot button — always available for a manual refresh */}
        <button
          onClick={onScreenshot}
          title="Capture a fresh screenshot"
          className="flex items-center gap-1 rounded-md border border-success/30 bg-success/10 px-2.5 py-1.5 text-xs text-success transition-colors hover:bg-success/20"
        >
          <Camera className="h-3 w-3" />
          Screenshot
        </button>

        <div className="h-4 w-px bg-border" />

        {/* Type input */}
        <div className="flex flex-1 items-center gap-1.5">
          <input
            type="text"
            value={typeText}
            onChange={(e) => setTypeText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleType()}
            placeholder="Type text..."
            className={cn(
              "flex-1 rounded-md border border-border bg-bg-secondary px-3 py-1.5",
              "text-xs text-text-primary placeholder:text-text-secondary/60",
              "outline-none focus:border-success/50 focus:ring-1 focus:ring-success/20",
            )}
          />
          <button
            onClick={handleType}
            disabled={!typeText.trim()}
            className={cn(
              "flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-xs transition-colors",
              "disabled:cursor-not-allowed disabled:opacity-50",
              typeText.trim()
                ? "border-success/30 bg-success/10 text-success hover:bg-success/20"
                : "border-border text-text-secondary",
            )}
          >
            <Type className="h-3 w-3" />
            Type
          </button>
        </div>

        {/* Keypress dropdown */}
        <select
          onChange={(e) => {
            const idx = parseInt(e.target.value);
            if (!isNaN(idx)) {
              onKeypress(COMMON_KEYS[idx].keys);
              e.target.value = "";
            }
          }}
          defaultValue=""
          className={cn(
            "rounded-md border border-border bg-bg-secondary px-2.5 py-1.5",
            "text-xs text-text-secondary outline-none",
            "focus:border-success/50",
          )}
        >
          <option value="" disabled>
            Keypress...
          </option>
          {COMMON_KEYS.map((k, i) => (
            <option key={k.label} value={i}>
              {k.label}
            </option>
          ))}
        </select>

        {/* Wait button */}
        <button
          onClick={onWait}
          className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs text-text-secondary transition-colors hover:bg-bg-secondary hover:text-text-primary"
        >
          <Timer className="h-3 w-3" />
          Wait
        </button>

        <div className="h-4 w-px bg-border" />

        {/* Done / Cancel */}
        <button
          onClick={onCancel}
          className="flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-xs text-text-secondary transition-colors hover:border-danger/50 hover:bg-danger/10 hover:text-danger"
        >
          <X className="h-3 w-3" />
          Cancel
        </button>
        <button
          onClick={onDone}
          disabled={steps.length === 0}
          className={cn(
            "flex items-center gap-1.5 rounded-md border px-4 py-1.5 text-xs font-medium transition-colors",
            "disabled:cursor-not-allowed disabled:opacity-50",
            steps.length > 0
              ? "border-success/30 bg-success/10 text-success hover:border-success hover:bg-success/20"
              : "border-border text-text-secondary",
          )}
        >
          <CheckCircle2 className="h-3.5 w-3.5" />
          Done ({steps.length} steps)
        </button>
      </div>
    </div>
  );
}

function StepIcon({ type }: { type: string }) {
  const cls = "h-3 w-3 text-text-secondary";
  switch (type) {
    case "click":
      return <MousePointerClick className={cls} />;
    case "type":
      return <Type className={cls} />;
    case "keypress":
      return <Keyboard className={cls} />;
    case "wait":
      return <Timer className={cls} />;
    default:
      return null;
  }
}

function describeStep(step: TeachStep): string {
  switch (step.type) {
    case "click":
      return `Click at (${step.x}, ${step.y})`;
    case "type":
      return `Type "${step.text}"`;
    case "keypress":
      return `Press ${(step.keys ?? []).join(" + ")}`;
    case "wait":
      return "Wait for screen update";
    default:
      return step.type;
  }
}
