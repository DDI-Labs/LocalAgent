import { Activity, Cpu, Zap, ShieldX, Hand, GraduationCap } from "lucide-react";
import { cn } from "@/lib/utils";

interface StatCardsProps {
  isConnected: boolean;
  currentTask: string;
  isHitlWaiting?: boolean;
  isTrainingMode?: boolean;
}

export function StatCards({ isConnected, currentTask, isHitlWaiting = false, isTrainingMode = false }: StatCardsProps) {
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
      label: "System",
      value: isTrainingMode ? "Training Mode" : "localhost:8000",
      icon: isTrainingMode ? GraduationCap : Cpu,
      dot: true,
      dotColor: isTrainingMode ? "bg-accent" : isConnected ? "bg-success" : "bg-danger",
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
