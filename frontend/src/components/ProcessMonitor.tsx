import { useRef, useEffect } from "react";
import { Terminal, Trash2 } from "lucide-react";
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
  info: "text-text-secondary",
};

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
          logs.map((log) => (
            <div key={log.id} className="flex gap-2">
              <span className="shrink-0 text-text-secondary/50">
                [{log.timestamp}]
              </span>
              <span
                className={cn(
                  "shrink-0 font-medium uppercase",
                  statusColor[log.status] ?? "text-text-secondary",
                )}
              >
                {log.status}
              </span>
              <span className="text-text-primary">{log.msg}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
