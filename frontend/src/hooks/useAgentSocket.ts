import { useState, useCallback, useRef, useEffect } from "react";
import useWebSocket, { ReadyState } from "react-use-websocket";

export interface LogEntry {
  id: number;
  timestamp: string;
  status: string;
  msg: string;
}

const WS_URL = "ws://localhost:8000/ws";
const API_BASE = "http://localhost:8000";

export function useAgentSocket() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [currentTask, setCurrentTask] = useState("Idle");
  const [isAgentBusy, setIsAgentBusy] = useState(false);
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

        if (data.status === "done") {
          setCurrentTask("Idle");
          setIsAgentBusy(false);
        } else if (data.status === "error") {
          setCurrentTask("Error");
          setIsAgentBusy(false);
        } else if (data.status === "thinking") {
          setCurrentTask(data.msg?.slice(0, 40) ?? "Thinking...");
          setIsAgentBusy(true);
        } else if (data.status === "info") {
          // info messages (e.g. history reset) don't change busy state
        } else {
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
  }, [sendMessage]);

  const clearLogs = useCallback(() => setLogs([]), []);

  return {
    logs,
    currentTask,
    isConnected,
    isAgentBusy,
    sendPrompt,
    resetHistory,
    clearLogs,
  };
}
