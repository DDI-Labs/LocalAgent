import { Bot } from "lucide-react";

export function Sidebar() {
  return (
    <aside className="flex w-60 flex-col border-r border-border bg-bg-secondary">
      {/* Logo */}
      <div className="flex items-center gap-3 border-b border-border px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15">
          <Bot className="h-5 w-5 text-accent" />
        </div>
        <div>
          <h1 className="text-sm font-semibold text-text-primary">LocalAgent</h1>
          <p className="text-xs text-text-secondary">macOS Automation</p>
        </div>
      </div>

      {/* Footer */}
      <div className="mt-auto border-t border-border px-5 py-4">
        <p className="text-xs text-text-secondary">v0.1.0 MVP</p>
      </div>
    </aside>
  );
}
