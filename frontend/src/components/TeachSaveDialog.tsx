import { useState } from "react";
import { Save, X, Plus, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TeachStep } from "@/hooks/useAgentSocket";

interface TeachSaveDialogProps {
  prompt: string;
  steps: TeachStep[];
  onSave: (name: string, triggers: string[], approvalRequired: boolean) => void;
  onCancel: () => void;
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 50)
    .replace(/-$/, "");
}

export function TeachSaveDialog({
  prompt,
  steps,
  onSave,
  onCancel,
}: TeachSaveDialogProps) {
  const [name, setName] = useState(slugify(prompt));
  const [triggers, setTriggers] = useState<string[]>([prompt]);
  const [newTrigger, setNewTrigger] = useState("");
  const [approvalRequired, setApprovalRequired] = useState(false);

  const handleAddTrigger = () => {
    const trimmed = newTrigger.trim();
    if (trimmed && !triggers.includes(trimmed)) {
      setTriggers([...triggers, trimmed]);
      setNewTrigger("");
    }
  };

  const handleRemoveTrigger = (idx: number) => {
    setTriggers(triggers.filter((_, i) => i !== idx));
  };

  const handleSave = () => {
    if (!name.trim() || triggers.length === 0) return;
    onSave(name.trim(), triggers, approvalRequired);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="mx-4 w-full max-w-lg rounded-xl border border-border bg-bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-text-primary">
            Save Skill
          </h2>
          <button
            onClick={onCancel}
            className="rounded-md p-1 text-text-secondary transition-colors hover:bg-bg-secondary hover:text-text-primary"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          {/* Name */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary uppercase">
              Skill Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={cn(
                "w-full rounded-lg border border-border bg-bg-secondary px-3 py-2",
                "text-sm text-text-primary outline-none",
                "focus:border-accent/50 focus:ring-1 focus:ring-accent/20",
              )}
            />
          </div>

          {/* Trigger phrases */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary uppercase">
              Trigger Phrases
            </label>
            <div className="space-y-1.5">
              {triggers.map((t, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 rounded-md border border-border bg-bg-secondary px-3 py-1.5"
                >
                  <span className="flex-1 text-sm text-text-primary">{t}</span>
                  {triggers.length > 1 && (
                    <button
                      onClick={() => handleRemoveTrigger(i)}
                      className="text-text-secondary transition-colors hover:text-danger"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  )}
                </div>
              ))}
            </div>
            <div className="mt-2 flex gap-1.5">
              <input
                type="text"
                value={newTrigger}
                onChange={(e) => setNewTrigger(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAddTrigger()}
                placeholder="Add another trigger phrase..."
                className={cn(
                  "flex-1 rounded-md border border-border bg-bg-secondary px-3 py-1.5",
                  "text-xs text-text-primary placeholder:text-text-secondary/60",
                  "outline-none focus:border-accent/50",
                )}
              />
              <button
                onClick={handleAddTrigger}
                disabled={!newTrigger.trim()}
                className="flex items-center gap-1 rounded-md border border-border px-2 py-1.5 text-xs text-text-secondary transition-colors hover:bg-bg-secondary hover:text-text-primary disabled:opacity-50"
              >
                <Plus className="h-3 w-3" />
                Add
              </button>
            </div>
          </div>

          {/* Approval required */}
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={approvalRequired}
              onChange={(e) => setApprovalRequired(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-border accent-accent"
            />
            <span className="text-xs text-text-secondary">
              Require approval before executing this skill
            </span>
          </label>

          {/* Step preview */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary uppercase">
              Recorded Steps ({steps.length})
            </label>
            <div className="max-h-32 overflow-y-auto rounded-lg border border-border bg-terminal-bg p-3">
              {steps.map((step, i) => (
                <div
                  key={i}
                  className="font-mono text-xs text-text-secondary"
                >
                  {i + 1}. {describeStep(step)}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-border px-6 py-4">
          <button
            onClick={onCancel}
            className="rounded-lg border border-border px-4 py-2 text-sm text-text-secondary transition-colors hover:bg-bg-secondary hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!name.trim() || triggers.length === 0}
            className={cn(
              "flex items-center gap-1.5 rounded-lg border px-5 py-2 text-sm font-medium transition-colors",
              "disabled:cursor-not-allowed disabled:opacity-50",
              "border-success/30 bg-success/10 text-success hover:border-success hover:bg-success/20",
            )}
          >
            <Save className="h-4 w-4" />
            Save Skill
          </button>
        </div>
      </div>
    </div>
  );
}

function describeStep(step: TeachStep): string {
  switch (step.type) {
    case "click":
      return `Click (${step.x}, ${step.y})`;
    case "type":
      return `Type "${step.text}"`;
    case "keypress":
      return `Press ${(step.keys ?? []).join("+")}`;
    case "wait":
      return "Wait";
    default:
      return step.type;
  }
}
