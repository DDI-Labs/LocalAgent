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
/** Payload sent by the backend when the agent needs human input. */
export interface HITLRequest {
  /** "takeover" = agent stuck, click to help. "approval" = sensitive action needs yes/no. "skill_approval" = approve a skill. */
  mode: "takeover" | "approval" | "skill_approval";
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

/** Which layer is handling the current task. */
export type ExecutionLayer =
  | "idle"
  | "macro"
  | "adapter"
  | "skill"
  | "vision"
  | "error";

/** A single step recorded during teach mode. */
export interface TeachStep {
  type: "click" | "type" | "keypress" | "wait";
  x?: number;
  y?: number;
  text?: string;
  keys?: string[];
}

const WS_URL = "ws://localhost:5757/ws";

export function useAgentSocket() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [currentTask, setCurrentTask] = useState("Idle");
  const [isAgentBusy, setIsAgentBusy] = useState(false);
  const [latestScreenshot, setLatestScreenshot] = useState<ScreenshotData | null>(null);
  const [hitlRequest, setHitlRequest] = useState<HITLRequest | null>(null);
  const [isTrainingMode, setIsTrainingMode] = useState(false);
  const [correctionMode, setCorrectionMode] = useState(false);
  const [executionLayer, setExecutionLayer] = useState<ExecutionLayer>("idle");
  const logIdRef = useRef(0);

  // --- Teach mode state ---
  const [isTeachMode, setIsTeachMode] = useState(false);
  const [teachSteps, setTeachSteps] = useState<TeachStep[]>([]);
  const [teachPrompt, setTeachPrompt] = useState("");
  const [showTeachSave, setShowTeachSave] = useState(false);

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

        // --- Teach mode sync ---
        if (data.teach_active !== undefined) {
          setIsTeachMode(data.teach_active);
          if (!data.teach_active) {
            // Teach ended — clear state
            setTeachSteps([]);
            setShowTeachSave(false);
          }
        }
        if (data.status === "teach_screenshot" && data.teach_step) {
          setTeachSteps((prev) => [...prev, data.teach_step]);
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

        // Parse execution layer from info messages
        if (data.execution_layer) {
          setExecutionLayer(data.execution_layer as ExecutionLayer);
        } else if (data.msg?.includes("Skill matched:")) {
          setExecutionLayer("skill");
        } else if (data.msg?.includes("fast-path")) {
          setExecutionLayer("macro");
        } else if (data.msg?.includes("adapter:")) {
          setExecutionLayer("adapter");
        }

        if (data.status === "done") {
          setCurrentTask("Idle");
          setIsAgentBusy(false);
          setExecutionLayer("idle");
        } else if (data.status === "error") {
          setCurrentTask("Error");
          setIsAgentBusy(false);
          setExecutionLayer("error");
        } else if (data.status === "blocked") {
          setCurrentTask("Blocked");
          setIsAgentBusy(false);
        } else if (data.status === "thinking") {
          setCurrentTask(data.msg?.slice(0, 40) ?? "Thinking...");
          setIsAgentBusy(true);
          if (executionLayer === "idle") setExecutionLayer("vision");
        } else if (data.status === "teach_screenshot") {
          setCurrentTask(`Teaching (${data.teach_step_count ?? 0} steps)`);
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
    setExecutionLayer("idle");
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

  // --- Teach mode senders ---

  /** Start teach mode — user will demonstrate the task step by step. */
  const startTeach = useCallback(
    (prompt: string) => {
      setTeachPrompt(prompt);
      setTeachSteps([]);
      setIsTeachMode(true);
      setShowTeachSave(false);
      sendMessage(JSON.stringify({ type: "teach_start", content: prompt }));
    },
    [sendMessage],
  );

  /** Request a fresh screenshot during teach mode. */
  const sendTeachScreenshot = useCallback(() => {
    sendMessage(JSON.stringify({ type: "teach_screenshot" }));
  }, [sendMessage]);

  /** Record a click during teach mode. */
  const sendTeachClick = useCallback(
    (x: number, y: number) => {
      sendMessage(JSON.stringify({ type: "teach_action", action: "click", x, y }));
    },
    [sendMessage],
  );

  /** Record a type action during teach mode. */
  const sendTeachType = useCallback(
    (text: string) => {
      sendMessage(
        JSON.stringify({ type: "teach_action", action: "type", text }),
      );
    },
    [sendMessage],
  );

  /** Record a keypress during teach mode. */
  const sendTeachKeypress = useCallback(
    (keys: string[]) => {
      sendMessage(
        JSON.stringify({ type: "teach_action", action: "keypress", keys }),
      );
    },
    [sendMessage],
  );

  /** Record a wait during teach mode. */
  const sendTeachWait = useCallback(() => {
    sendMessage(JSON.stringify({ type: "teach_action", action: "wait" }));
  }, [sendMessage]);

  /** Show the save dialog after teaching is done. */
  const finishTeach = useCallback(() => {
    setShowTeachSave(true);
  }, []);

  /** Save the taught skill and exit teach mode. */
  const saveTeachSkill = useCallback(
    (name: string, triggers: string[], approvalRequired: boolean) => {
      sendMessage(
        JSON.stringify({
          type: "teach_done",
          name,
          trigger_phrases: triggers,
          approval_required: approvalRequired,
          description: teachPrompt,
        }),
      );
      setIsTeachMode(false);
      setTeachSteps([]);
      setShowTeachSave(false);
      setTeachPrompt("");
    },
    [sendMessage, teachPrompt],
  );

  /** Cancel teach mode without saving. */
  const cancelTeach = useCallback(() => {
    sendMessage(JSON.stringify({ type: "teach_cancel" }));
    setIsTeachMode(false);
    setTeachSteps([]);
    setShowTeachSave(false);
    setTeachPrompt("");
  }, [sendMessage]);

  return {
    logs,
    currentTask,
    isConnected,
    isAgentBusy,
    latestScreenshot,
    hitlRequest,
    correctionMode,
    executionLayer,
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
    // Teach mode
    isTeachMode,
    teachSteps,
    teachPrompt,
    showTeachSave,
    startTeach,
    sendTeachScreenshot,
    sendTeachClick,
    sendTeachType,
    sendTeachKeypress,
    sendTeachWait,
    finishTeach,
    saveTeachSkill,
    cancelTeach,
  };
}
