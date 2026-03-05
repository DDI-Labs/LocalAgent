import { LayoutDashboard, ScrollText, Settings, Bot } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { icon: LayoutDashboard, label: "Dashboard", active: true },
  { icon: ScrollText, label: "Automation Logs", active: false },
  { icon: Settings, label: "Settings", active: false },
];

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

      {/* Nav */}
      <nav className="flex-1 px-3 py-4">
        <ul className="space-y-1">
          {navItems.map((item) => (
            <li key={item.label}>
              <button
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                  item.active
                    ? "bg-accent/10 text-accent"
                    : "text-text-secondary hover:bg-bg-card hover:text-text-primary",
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* Footer */}
      <div className="border-t border-border px-5 py-4">
        <p className="text-xs text-text-secondary">v0.1.0 MVP</p>
      </div>
    </aside>
  );
}
