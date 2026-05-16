import { useState } from "react";
import BriefForm from "./components/BriefForm";
import AgentTrace from "./components/AgentTrace";
import BriefOutput from "./components/BriefOutput";
import "./index.css";

export default function App() {
  const [phase, setPhase] = useState("idle"); // idle | running | done | error
  const [traceEvents, setTraceEvents] = useState([]);
  const [brief, setBrief] = useState("");
  const [error, setError] = useState("");

  const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

  const runBrief = async ({ city, interests, focusToday }) => {
    setPhase("running");
    setTraceEvents([]);
    setBrief("");
    setError("");

    try {
      const res = await fetch(`${API_BASE}/brief`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          city,
          interests,
          focus_today: focusToday,
        }),
      });

      if (!res.ok) throw new Error(`Server error: ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          try {
            const event = JSON.parse(raw);
            if (event.type === "tool_call" || event.type === "tool_result") {
              setTraceEvents((prev) => [...prev, event]);
            } else if (event.type === "brief") {
              setBrief(event.content);
              setPhase("done");
            } else if (event.type === "error") {
              setError(event.message);
              setPhase("error");
            }
          } catch {
            // skip malformed events
          }
        }
      }
    } catch (e) {
      setError(e.message || "Something went wrong.");
      setPhase("error");
    }
  };

  const reset = () => {
    setPhase("idle");
    setTraceEvents([]);
    setBrief("");
    setError("");
  };

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-mark">◈</span>
            <span className="logo-text">DailyBrief</span>
          </div>
          <p className="tagline">Your agentic morning intelligence</p>
        </div>
      </header>

      <main className="main">
        {phase === "idle" && <BriefForm onSubmit={runBrief} />}

        {(phase === "running" || phase === "done") && (
          <div className="workspace">
            <AgentTrace events={traceEvents} isRunning={phase === "running"} />
            {brief && <BriefOutput content={brief} onReset={reset} />}
          </div>
        )}

        {phase === "error" && (
          <div className="error-state">
            <p className="error-icon">⚠</p>
            <p className="error-msg">{error}</p>
            <button className="btn-reset" onClick={reset}>
              Try again
            </button>
          </div>
        )}
      </main>

      <footer className="footer">
        <p>Powered by Groq · LLaMA 3.1 8B · Built for humans</p>
      </footer>
    </div>
  );
}
