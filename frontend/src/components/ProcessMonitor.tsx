import { useRef, useEffect } from "react";
import {
  Terminal,
  Trash2,
  Brain,
  Play,
  CheckCircle2,
  XCircle,
  ShieldX,
  Info,
  Hand,
  Bolt,
  Puzzle,
  Layers,
  Eye,
} from "lucide-react";
import type { LogEntry } from "@/hooks/useAgentSocket";
import { cn } from "@/lib/utils";

interface ProcessMonitorProps {
  logs: LogEntry[];
  onClear: () => void;
}

const statusColor: Record<string, string> = {
  thinking: "text-warning",
  action: "text-accent",
  done: "text-success",
  error: "text-danger",
  blocked: "text-blocked",
  info: "text-text-secondary",
  waiting_for_human: "text-warning",
  teach_screenshot: "text-success",
};

const statusIcon: Record<string, typeof Terminal> = {
  thinking: Brain,
  action: Play,
  done: CheckCircle2,
  error: XCircle,
  blocked: ShieldX,
  info: Info,
  waiting_for_human: Hand,
  teach_screenshot: Layers,
};

function getLayerIndicator(msg: string): { icon: typeof Terminal; color: string } | null {
  if (msg.includes("fast-path") || msg.includes("macro")) return { icon: Bolt, color: "text-success" };
  if (msg.includes("adapter:") || msg.includes("Adapter")) return { icon: Puzzle, color: "text-accent" };
  if (msg.includes("Skill matched") || msg.includes("skill")) return { icon: Layers, color: "text-warning" };
  if (msg.includes("vision") || msg.includes("Processing:")) return { icon: Eye, color: "text-danger" };
  return null;
}

export function ProcessMonitor({ logs, onClear }: ProcessMonitorProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="flex flex-col rounded-xl border border-border bg-bg-card">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-terminal-green" />
          <span className="text-sm font-semibold tracking-wide text-text-secondary uppercase">
            Process Monitor
          </span>
          <span className="rounded-full bg-bg-secondary px-2 py-0.5 text-xs text-text-secondary">
            {logs.length}
          </span>
        </div>
        <button
          onClick={onClear}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-text-secondary transition-colors hover:bg-bg-secondary hover:text-text-primary"
        >
          <Trash2 className="h-3 w-3" />
          Clear Logs
        </button>
      </div>

      {/* Terminal body */}
      <div className="terminal-scroll h-64 overflow-y-auto bg-terminal-bg p-4 font-mono text-xs leading-relaxed">
        {logs.length === 0 ? (
          <p className="text-text-secondary">
            Waiting for agent activity...
          </p>
        ) : (
          logs.map((log) => {
            const Icon = statusIcon[log.status];
            const color = statusColor[log.status] ?? "text-text-secondary";
            const layerHint = getLayerIndicator(log.msg);
            return (
              <div key={log.id} className="flex items-start gap-2">
                <span className="shrink-0 text-text-secondary/50">
                  [{log.timestamp}]
                </span>
                {layerHint && (
                  <layerHint.icon className={cn("h-3 w-3 shrink-0 mt-0.5", layerHint.color)} />
                )}
                <span
                  className={cn(
                    "flex shrink-0 items-center gap-1 font-medium uppercase",
                    color,
                  )}
                >
                  {Icon && <Icon className="h-3 w-3" />}
                  {log.status}
                </span>
                <span className="text-text-primary">{log.msg}</span>
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
