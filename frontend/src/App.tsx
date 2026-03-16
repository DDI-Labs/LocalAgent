import { Sidebar } from "@/components/Sidebar";
import { StatCards } from "@/components/StatCards";
import { ChatInput } from "@/components/ChatInput";
import { ProcessMonitor } from "@/components/ProcessMonitor";
import { ScreenshotViewer } from "@/components/ScreenshotViewer";
import { HITLOverlay } from "@/components/HITLOverlay";
import { useAgentSocket } from "@/hooks/useAgentSocket";

function App() {
  const {
    logs,
    currentTask,
    isConnected,
    isAgentBusy,
    latestScreenshot,
    hitlRequest,
    correctionMode,
    sendPrompt,
    resetHistory,
    clearLogs,
    isTrainingMode,
    sendHitlClick,
    sendHitlApprove,
    sendHitlReject,
    sendHitlCancel,
    enterCorrectionMode,
    sendHitlCorrection,
    toggleTrainingMode,
  } = useAgentSocket();

  const isTakeover = hitlRequest?.mode === "takeover";
  const isClickable = isTakeover || correctionMode;

  return (
    <div className="flex h-screen bg-bg-primary">
      <Sidebar />

      <main className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto flex max-w-5xl flex-col gap-5">
          {/* Top row: stat cards */}
          <StatCards
            isConnected={isConnected}
            currentTask={currentTask}
            isHitlWaiting={hitlRequest != null}
            isTrainingMode={isTrainingMode}
          />

          {/* Agent chat input */}
          <ChatInput
            isLoading={isAgentBusy}
            isTrainingMode={isTrainingMode}
            onSend={sendPrompt}
            onReset={resetHistory}
            onToggleTraining={toggleTrainingMode}
          />

          {/* HITL overlay — shown when the agent needs human help */}
          {hitlRequest && (
            <HITLOverlay
              request={hitlRequest}
              correctionMode={correctionMode}
              onApprove={sendHitlApprove}
              onReject={sendHitlReject}
              onCancel={sendHitlCancel}
              onEnterCorrection={enterCorrectionMode}
              onSkip={sendHitlReject}
            />
          )}

          {/* Live screenshot view — shows what the agent sees + click targets */}
          <ScreenshotViewer
            data={latestScreenshot}
            takeoverMode={isClickable}
            onTakeoverClick={
              isTakeover
                ? sendHitlClick
                : correctionMode
                  ? sendHitlCorrection
                  : undefined
            }
            proposedClick={hitlRequest?.proposed_click}
          />

          {/* Process monitor — agent reasoning + actions */}
          <ProcessMonitor logs={logs} onClear={clearLogs} />
        </div>
      </main>
    </div>
  );
}

export default App;
