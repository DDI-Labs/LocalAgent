import { useState, useRef, useEffect } from "react";
import { Send, Loader2, RotateCcw, GraduationCap, BookOpen, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  isLoading: boolean;
  isTrainingMode: boolean;
  isTeachMode: boolean;
  teachPrompt: string;
  onSend: (prompt: string) => void;
  onTeach: (prompt: string) => void;
  onCancelTeach: () => void;
  onReset: () => void;
  onToggleTraining: () => void;
}

const QUICK_ACTIONS = [
  "Open Spotify",
  "Play some music",
  "Skip track",
  "Pause music",
  "Search for Bohemian Rhapsody",
];

export function ChatInput({
  isLoading,
  isTrainingMode,
  isTeachMode,
  teachPrompt,
  onSend,
  onTeach,
  onCancelTeach,
  onReset,
  onToggleTraining,
}: ChatInputProps) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isLoading && !isTeachMode) inputRef.current?.focus();
  }, [isLoading, isTeachMode]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "/" && !isTeachMode && document.activeElement !== inputRef.current) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isTeachMode]);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setInput("");
  };

  const handleTeach = () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onTeach(trimmed);
    setInput("");
  };

  return (
    <div className="rounded-xl border border-border bg-bg-card p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-wide text-text-secondary uppercase">
          Agent Control
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={onToggleTraining}
            className={cn(
              "flex items-center gap-1 rounded-md px-2 py-1 text-xs transition-colors",
              isTrainingMode
                ? "bg-accent/15 text-accent border border-accent/30"
                : "text-text-secondary hover:bg-bg-secondary hover:text-text-primary",
            )}
          >
            <GraduationCap className="h-3 w-3" />
            {isTrainingMode ? "Training On" : "Train"}
          </button>
          <button
            onClick={onReset}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-text-secondary transition-colors hover:bg-bg-secondary hover:text-text-primary"
          >
            <RotateCcw className="h-3 w-3" />
            Reset
          </button>
        </div>
      </div>

      {/* Teach mode active banner */}
      {isTeachMode ? (
        <div className="flex items-center justify-between rounded-lg border border-success/30 bg-success/10 px-4 py-3">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-success" />
            <span className="text-sm font-medium text-success">Teaching:</span>
            <span className="text-sm text-text-primary">{teachPrompt}</span>
          </div>
          <button
            onClick={onCancelTeach}
            className={cn(
              "flex items-center gap-1 rounded-md border border-border px-2 py-1",
              "text-xs text-text-secondary transition-colors",
              "hover:border-danger/50 hover:bg-danger/10 hover:text-danger",
            )}
          >
            <X className="h-3 w-3" />
            Cancel
          </button>
        </div>
      ) : (
        <>
          {/* Input row */}
          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) handleSubmit();
                if (e.key === "Escape") inputRef.current?.blur();
              }}
              disabled={isLoading}
              placeholder={
                isLoading
                  ? "Agent is working..."
                  : "Tell the agent what to do..."
              }
              className={cn(
                "flex-1 rounded-lg border border-border bg-bg-secondary px-4 py-2.5",
                "text-sm text-text-primary placeholder:text-text-secondary/60",
                "outline-none transition-colors",
                "focus:border-accent/50 focus:ring-1 focus:ring-accent/20",
                "disabled:cursor-not-allowed disabled:opacity-50",
              )}
            />
            {/* Teach button */}
            <button
              onClick={handleTeach}
              disabled={isLoading || !input.trim()}
              title="Teach this task by demonstrating it step by step"
              className={cn(
                "flex items-center justify-center rounded-lg border px-3 transition-all",
                "disabled:cursor-not-allowed disabled:opacity-50",
                input.trim() && !isLoading
                  ? "border-success/30 bg-success/10 text-success hover:border-success hover:bg-success/20"
                  : "border-border bg-bg-secondary text-text-secondary",
              )}
            >
              <BookOpen className="h-4 w-4" />
            </button>
            {/* Send button */}
            <button
              onClick={handleSubmit}
              disabled={isLoading || !input.trim()}
              className={cn(
                "flex items-center justify-center rounded-lg border px-4 transition-all",
                "disabled:cursor-not-allowed disabled:opacity-50",
                input.trim() && !isLoading
                  ? "border-accent/30 bg-accent/10 text-accent hover:border-accent hover:bg-accent/20"
                  : "border-border bg-bg-secondary text-text-secondary",
              )}
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </button>
          </div>

          {/* Quick action chips */}
          <div className="mt-3 flex flex-wrap gap-2">
            {QUICK_ACTIONS.map((action) => (
              <button
                key={action}
                disabled={isLoading}
                onClick={() => {
                  if (!isLoading) onSend(action);
                }}
                className={cn(
                  "rounded-full border border-border bg-bg-secondary px-3 py-1",
                  "text-xs text-text-secondary transition-colors",
                  "hover:border-text-secondary hover:text-text-primary",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                )}
              >
                {action}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
