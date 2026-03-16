import { useState, useCallback, useRef } from "react";
import useWebSocket, { ReadyState } from "react-use-websocket";

export interface LogEntry {
  id: number;
  timestamp: string;
  status: string;
  msg: string;
}

export interface ScreenshotData {
  /** data:image/... URL */
  image: string;
  /** Click coordinates (in screenshot space) if the action was a click */
  click?: { x: number; y: number };
  /** Timestamp for display */
  timestamp: string;
}

/** Payload sent by the backend when the agent needs human input. */
export interface HITLRequest {
  /** "takeover" = agent stuck, click to help. "approval" = sensitive action needs yes/no. */
  mode: "takeover" | "approval";
  /** Human-readable description of the proposed action (approval mode). */
  action_description?: string;
  /** The keyword that triggered the approval gate. */
  matched_keyword?: string;
  /** Truncated planning model reasoning for context. */
  reasoning?: string;
  /** Screenshot to display (takeover mode sends this at top level too). */
  screenshot?: string;
  /** Proposed click coordinates — where the agent wants to click (click/double_click actions). */
  proposed_click?: { x: number; y: number };
}

const WS_URL = "ws://localhost:8000/ws";

export function useAgentSocket() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [currentTask, setCurrentTask] = useState("Idle");
  const [isAgentBusy, setIsAgentBusy] = useState(false);
  const [latestScreenshot, setLatestScreenshot] = useState<ScreenshotData | null>(null);
  const [hitlRequest, setHitlRequest] = useState<HITLRequest | null>(null);
  const [isTrainingMode, setIsTrainingMode] = useState(false);
  const [correctionMode, setCorrectionMode] = useState(false);
  const logIdRef = useRef(0);

  const { sendMessage, readyState } = useWebSocket(WS_URL, {
    onMessage: (event) => {
      try {
        const data = JSON.parse(event.data);
        const entry: LogEntry = {
          id: logIdRef.current++,
          timestamp: new Date().toLocaleTimeString(),
          status: data.status ?? "info",
          msg: data.msg ?? JSON.stringify(data),
        };
        setLogs((prev) => [...prev, entry]);

        // Update screenshot viewer when a screenshot is included
        if (data.screenshot) {
          setLatestScreenshot({
            image: data.screenshot,
            click: data.click ?? undefined,
            timestamp: entry.timestamp,
          });
        }

        // --- Training mode sync ---
        if (data.training_mode !== undefined) {
          setIsTrainingMode(data.training_mode);
        }

        // --- HITL handling ---
        if (data.status === "waiting_for_human" && data.hitl) {
          const hitl: HITLRequest = {
            mode: data.hitl.mode,
            action_description: data.hitl.action_description,
            matched_keyword: data.hitl.matched_keyword,
            reasoning: data.hitl.reasoning,
            screenshot: data.screenshot,
            proposed_click: data.hitl.proposed_click ?? undefined,
          };
          setHitlRequest(hitl);
          setCurrentTask("Waiting for human");
          setIsAgentBusy(true);
          return;
        }

        // Clear HITL on terminal statuses
        if (
          data.status === "done" ||
          data.status === "error" ||
          data.status === "blocked"
        ) {
          setHitlRequest(null);
          setCorrectionMode(false);
        }

        if (data.status === "done") {
          setCurrentTask("Idle");
          setIsAgentBusy(false);
        } else if (data.status === "error") {
          setCurrentTask("Error");
          setIsAgentBusy(false);
        } else if (data.status === "blocked") {
          setCurrentTask("Blocked");
          setIsAgentBusy(false);
        } else if (data.status === "thinking") {
          setCurrentTask(data.msg?.slice(0, 40) ?? "Thinking...");
          setIsAgentBusy(true);
        } else if (data.status === "info") {
          // info messages (e.g. history reset, HITL resume) — clear HITL if it was active
          setHitlRequest((prev) => {
            if (prev && data.msg?.includes("Takeover complete")) return null;
            if (prev && data.msg?.includes("approved")) return null;
            return prev;
          });
        } else if (data.status !== "waiting_for_human") {
          setCurrentTask(data.msg?.slice(0, 40) ?? data.status);
        }
      } catch {
        // Non-JSON message
      }
    },
    shouldReconnect: () => true,
    reconnectAttempts: Infinity,
    reconnectInterval: 3000,
  });

  const isConnected = readyState === ReadyState.OPEN;

  const sendPrompt = useCallback(
    (prompt: string) => {
      setIsAgentBusy(true);
      setCurrentTask("Starting...");
      sendMessage(JSON.stringify({ type: "prompt", content: prompt }));
    },
    [sendMessage],
  );

  const resetHistory = useCallback(() => {
    sendMessage(JSON.stringify({ type: "reset" }));
    setCurrentTask("Idle");
    setIsAgentBusy(false);
    setLatestScreenshot(null);
    setHitlRequest(null);
    setCorrectionMode(false);
  }, [sendMessage]);

  const clearLogs = useCallback(() => setLogs([]), []);

  // --- HITL response senders ---

  /** Send a takeover click (user clicked on the screenshot). */
  const sendHitlClick = useCallback(
    (x: number, y: number) => {
      sendMessage(
        JSON.stringify({
          type: "hitl_response",
          mode: "takeover",
          action: "click",
          x,
          y,
        }),
      );
      setHitlRequest(null);
      setCurrentTask("Resuming...");
    },
    [sendMessage],
  );

  /** Approve a sensitive action. */
  const sendHitlApprove = useCallback(() => {
    sendMessage(
      JSON.stringify({ type: "hitl_response", mode: "approval", approved: true }),
    );
    setHitlRequest(null);
    setCurrentTask("Resuming...");
  }, [sendMessage]);

  /** Reject a sensitive action (skip without correction). */
  const sendHitlReject = useCallback(() => {
    sendMessage(
      JSON.stringify({ type: "hitl_response", mode: "approval", approved: false }),
    );
    setHitlRequest(null);
    setCorrectionMode(false);
    setCurrentTask("Rejected");
    setIsAgentBusy(false);
  }, [sendMessage]);

  /** Enter correction mode — user rejected and wants to show the right click. */
  const enterCorrectionMode = useCallback(() => {
    setCorrectionMode(true);
  }, []);

  /** Send a correction click — replaces the agent's proposed click coordinates. */
  const sendHitlCorrection = useCallback(
    (x: number, y: number) => {
      sendMessage(
        JSON.stringify({
          type: "hitl_response",
          mode: "approval",
          approved: false,
          correction: { x, y },
        }),
      );
      setHitlRequest(null);
      setCorrectionMode(false);
      setCurrentTask("Resuming (corrected)...");
    },
    [sendMessage],
  );

  /** Cancel the HITL request entirely (stop the task). */
  const sendHitlCancel = useCallback(() => {
    sendMessage(JSON.stringify({ type: "hitl_response", mode: "cancel" }));
    setHitlRequest(null);
    setCorrectionMode(false);
    setCurrentTask("Idle");
    setIsAgentBusy(false);
  }, [sendMessage]);

  /** Toggle training mode (gate every action for human approval). */
  const toggleTrainingMode = useCallback(() => {
    const next = !isTrainingMode;
    sendMessage(JSON.stringify({ type: "training_mode", enabled: next }));
    setIsTrainingMode(next);
  }, [sendMessage, isTrainingMode]);

  return {
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
  };
}
