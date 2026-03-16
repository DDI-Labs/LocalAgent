import { ShieldAlert, MousePointerClick, Check, X, Ban, GraduationCap, Pointer } from "lucide-react";
import { cn } from "@/lib/utils";
import type { HITLRequest } from "@/hooks/useAgentSocket";

interface HITLOverlayProps {
  request: HITLRequest;
  /** Whether the user is in correction mode (rejected + showing correct click). */
  correctionMode?: boolean;
  onApprove: () => void;
  onReject: () => void;
  onCancel: () => void;
  /** Called when user clicks "Correct" in training mode to enter correction mode. */
  onEnterCorrection?: () => void;
  /** Called when user clicks "Skip" in correction mode to reject without correction. */
  onSkip?: () => void;
}

export function HITLOverlay({
  request,
  correctionMode = false,
  onApprove,
  onReject,
  onCancel,
  onEnterCorrection,
  onSkip,
}: HITLOverlayProps) {
  if (request.mode === "takeover") {
    return <TakeoverBanner onCancel={onCancel} />;
  }

  if (correctionMode) {
    return <CorrectionBanner onSkip={onSkip ?? onReject} onCancel={onCancel} />;
  }

  return (
    <ApprovalDialog
      request={request}
      onApprove={onApprove}
      onReject={onReject}
      onCancel={onCancel}
      onEnterCorrection={onEnterCorrection}
    />
  );
}

/* ------- Takeover banner (shown above the screenshot) ------- */

function TakeoverBanner({ onCancel }: { onCancel: () => void }) {
  return (
    <div className="rounded-xl border-2 border-warning/50 bg-warning/10 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-lg bg-warning/20 p-2">
            <MousePointerClick className="h-5 w-5 text-warning" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-warning">
              Human Takeover Required
            </h3>
            <p className="mt-1 text-xs leading-relaxed text-text-secondary">
              The agent is stuck and needs your help. Click directly on the
              screenshot below where the agent should click to continue.
            </p>
          </div>
        </div>
        <button
          onClick={onCancel}
          className={cn(
            "shrink-0 rounded-lg border border-border px-3 py-1.5",
            "text-xs text-text-secondary transition-colors",
            "hover:border-danger/50 hover:bg-danger/10 hover:text-danger",
          )}
        >
          <span className="flex items-center gap-1">
            <Ban className="h-3 w-3" />
            Cancel Task
          </span>
        </button>
      </div>
    </div>
  );
}

/* ------- Correction banner (user rejected, now clicking correct location) ------- */

function CorrectionBanner({
  onSkip,
  onCancel,
}: {
  onSkip: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="rounded-xl border-2 border-accent/50 bg-accent/10 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-lg bg-accent/20 p-2">
            <Pointer className="h-5 w-5 text-accent" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-accent">
              Show Correct Click
            </h3>
            <p className="mt-1 text-xs leading-relaxed text-text-secondary">
              Click on the screenshot below where the agent <strong>should</strong> have
              clicked. The agent will execute your corrected action instead.
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            onClick={onSkip}
            className={cn(
              "rounded-lg border border-border px-3 py-1.5",
              "text-xs text-text-secondary transition-colors",
              "hover:border-text-secondary hover:text-text-primary",
            )}
          >
            <span className="flex items-center gap-1">
              <X className="h-3 w-3" />
              Skip
            </span>
          </button>
          <button
            onClick={onCancel}
            className={cn(
              "rounded-lg border border-border px-3 py-1.5",
              "text-xs text-text-secondary transition-colors",
              "hover:border-danger/50 hover:bg-danger/10 hover:text-danger",
            )}
          >
            <span className="flex items-center gap-1">
              <Ban className="h-3 w-3" />
              Cancel Task
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------- Approval dialog (for sensitive actions) ------- */

function ApprovalDialog({
  request,
  onApprove,
  onReject,
  onCancel,
  onEnterCorrection,
}: {
  request: HITLRequest;
  onApprove: () => void;
  onReject: () => void;
  onCancel: () => void;
  onEnterCorrection?: () => void;
}) {
  const isTraining = request.matched_keyword === "training";
  const borderColor = isTraining ? "border-accent/50" : "border-danger/50";
  const bgColor = isTraining ? "bg-accent/10" : "bg-danger/10";
  const iconBg = isTraining ? "bg-accent/20" : "bg-danger/20";
  const iconColor = isTraining ? "text-accent" : "text-danger";
  const Icon = isTraining ? GraduationCap : ShieldAlert;

  return (
    <div className={cn("rounded-xl border-2 p-4", borderColor, bgColor)}>
      <div className="flex items-start gap-3">
        <div className={cn("mt-0.5 rounded-lg p-2", iconBg)}>
          <Icon className={cn("h-5 w-5", iconColor)} />
        </div>
        <div className="flex-1">
          <h3 className={cn("text-sm font-semibold", iconColor)}>
            {isTraining ? "Training Step" : "Action Approval Required"}
          </h3>
          <p className="mt-1 text-xs text-text-secondary">
            {isTraining
              ? "The agent proposes the following action. Approve to execute, or reject to skip."
              : "The agent wants to perform a sensitive action. Review and approve or reject."}
          </p>

          {/* Action details */}
          <div className="mt-3 rounded-lg border border-border bg-bg-secondary p-3">
            {request.action_description && (
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-text-secondary uppercase">
                  Action:
                </span>
                <span className="font-mono text-xs text-text-primary">
                  {request.action_description}
                </span>
              </div>
            )}
            {request.matched_keyword && request.matched_keyword !== "training" && (
              <div className="mt-1.5 flex items-center gap-2">
                <span className="text-xs font-medium text-text-secondary uppercase">
                  Trigger:
                </span>
                <span className="rounded-full bg-danger/20 px-2 py-0.5 text-xs font-medium text-danger">
                  {request.matched_keyword}
                </span>
              </div>
            )}
            {request.reasoning && (
              <div className="mt-2 border-t border-border pt-2">
                <span className="text-xs font-medium text-text-secondary uppercase">
                  {isTraining ? "Grounding Output:" : "Context:"}
                </span>
                <p className="mt-1 font-mono text-xs leading-relaxed text-text-secondary">
                  {request.reasoning.length > 200
                    ? request.reasoning.slice(0, 200) + "..."
                    : request.reasoning}
                </p>
              </div>
            )}
          </div>

          {/* Action buttons */}
          <div className="mt-3 flex items-center gap-2">
            <button
              onClick={onApprove}
              className={cn(
                "flex items-center gap-1.5 rounded-lg border px-4 py-2",
                "border-success/30 bg-success/10 text-sm font-medium text-success",
                "transition-colors hover:border-success hover:bg-success/20",
              )}
            >
              <Check className="h-4 w-4" />
              Approve
            </button>
            {/* In training mode with a click action: show "Correct" to enter correction mode */}
            {isTraining && request.proposed_click && onEnterCorrection ? (
              <button
                onClick={onEnterCorrection}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg border px-4 py-2",
                  "border-accent/30 bg-accent/10 text-sm font-medium text-accent",
                  "transition-colors hover:border-accent hover:bg-accent/20",
                )}
              >
                <Pointer className="h-4 w-4" />
                Correct
              </button>
            ) : (
              <button
                onClick={onReject}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg border px-4 py-2",
                  "border-danger/30 bg-danger/10 text-sm font-medium text-danger",
                  "transition-colors hover:border-danger hover:bg-danger/20",
                )}
              >
                <X className="h-4 w-4" />
                Reject
              </button>
            )}
            {/* Show plain Reject alongside Correct in training mode */}
            {isTraining && request.proposed_click && onEnterCorrection && (
              <button
                onClick={onReject}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg border border-border px-4 py-2",
                  "text-sm text-text-secondary transition-colors",
                  "hover:border-danger/50 hover:bg-danger/10 hover:text-danger",
                )}
              >
                <X className="h-4 w-4" />
                Skip
              </button>
            )}
            <button
              onClick={onCancel}
              className={cn(
                "flex items-center gap-1.5 rounded-lg border border-border px-4 py-2",
                "text-sm text-text-secondary transition-colors",
                "hover:border-text-secondary hover:text-text-primary",
              )}
            >
              <Ban className="h-3.5 w-3.5" />
              Cancel Task
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
