import { Activity, Cpu, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

interface StatCardsProps {
  isConnected: boolean;
  currentTask: string;
}

export function StatCards({ isConnected, currentTask }: StatCardsProps) {
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
      icon: Zap,
      dot: false,
    },
    {
      label: "System",
      value: "localhost:8000",
      icon: Cpu,
      dot: true,
      dotColor: isConnected ? "bg-success" : "bg-danger",
    },
  ];

  return (
    <div className="grid grid-cols-3 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-xl border border-border bg-bg-card p-4 transition-colors hover:bg-bg-card-hover"
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
