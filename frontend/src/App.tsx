import { Sidebar } from "@/components/Sidebar";
import { StatCards } from "@/components/StatCards";
import { ChatInput } from "@/components/ChatInput";
import { ProcessMonitor } from "@/components/ProcessMonitor";
import { useAgentSocket } from "@/hooks/useAgentSocket";

function App() {
  const {
    logs,
    currentTask,
    isConnected,
    isAgentBusy,
    sendPrompt,
    resetHistory,
    clearLogs,
  } = useAgentSocket();

  return (
    <div className="flex h-screen bg-bg-primary">
      <Sidebar />

      <main className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto flex max-w-5xl flex-col gap-5">
          {/* Top row: stat cards */}
          <StatCards isConnected={isConnected} currentTask={currentTask} />

          {/* Agent chat input */}
          <ChatInput
            isLoading={isAgentBusy}
            onSend={sendPrompt}
            onReset={resetHistory}
          />

          {/* Process monitor — agent reasoning + actions */}
          <ProcessMonitor logs={logs} onClear={clearLogs} />
        </div>
      </main>
    </div>
  );
}

export default App;
