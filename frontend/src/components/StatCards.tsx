import { Activity, Zap, ShieldX, Hand, GraduationCap, Layers, Bolt, Eye, Puzzle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ExecutionLayer } from "@/hooks/useAgentSocket";

interface StatCardsProps {
  isConnected: boolean;
  currentTask: string;
  isHitlWaiting?: boolean;
  isTrainingMode?: boolean;
  executionLayer?: ExecutionLayer;
}

const layerConfig: Record<ExecutionLayer, { label: string; color: string; icon: typeof Zap }> = {
  idle: { label: "Idle", color: "bg-text-secondary", icon: Layers },
  macro: { label: "Macro", color: "bg-success", icon: Bolt },
  adapter: { label: "Adapter", color: "bg-accent", icon: Puzzle },
  skill: { label: "Skill", color: "bg-warning", icon: Layers },
  vision: { label: "Vision", color: "bg-danger", icon: Eye },
  error: { label: "Error", color: "bg-danger", icon: ShieldX },
};

export function StatCards({
  isConnected,
  currentTask,
  isHitlWaiting = false,
  isTrainingMode = false,
  executionLayer = "idle",
}: StatCardsProps) {
  const taskIcon = isHitlWaiting
    ? Hand
    : currentTask === "Blocked"
      ? ShieldX
      : Zap;

  const taskDot =
    isHitlWaiting ||
    currentTask === "Blocked" ||
    currentTask === "Error";

  const taskDotColor = isHitlWaiting
    ? "bg-warning"
    : currentTask === "Blocked"
      ? "bg-blocked"
      : "bg-danger";

  const layer = layerConfig[executionLayer];

  const cards = [
    {
      label: "Agent Status",
      value: isConnected ? "Online" : "Offline",
      icon: Activity,
      dot: true,
      dotColor: isConnected ? "bg-success" : "bg-danger",
    },
    {
      label: "Current Task",
      value: currentTask,
      icon: taskIcon,
      dot: taskDot,
      dotColor: taskDotColor,
    },
    {
      label: "Execution Layer",
      value: isTrainingMode ? "Training Mode" : layer.label,
      icon: isTrainingMode ? GraduationCap : layer.icon,
      dot: true,
      dotColor: isTrainingMode ? "bg-accent" : layer.color,
    },
  ];

  return (
    <div className="grid grid-cols-3 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className={cn(
            "rounded-xl border bg-bg-card p-4 transition-colors hover:bg-bg-card-hover",
            card.label === "Current Task" && isHitlWaiting
              ? "border-warning/40"
              : "border-border",
          )}
        >
          <div className="mb-3 flex items-center justify-between">
            <span className="text-xs font-medium tracking-wide text-text-secondary uppercase">
              {card.label}
            </span>
            <card.icon className="h-4 w-4 text-text-secondary" />
          </div>
          <div className="flex items-center gap-2">
            {card.dot && (
              <span
                className={cn(
                  "inline-block h-2 w-2 rounded-full animate-pulse-dot",
                  card.dotColor,
                )}
              />
            )}
            <span className="truncate text-sm font-semibold text-text-primary">
              {card.value}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
