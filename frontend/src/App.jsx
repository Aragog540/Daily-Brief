import { useState, useEffect } from "react";
import BriefForm from "./components/BriefForm";
import AgentTrace from "./components/AgentTrace";
import BriefOutput from "./components/BriefOutput";
import "./index.css";
import Auth from "./components/Auth";
import { supabase } from "./supabaseClient";
import ProfileCity from "./components/ProfileCity";

export default function App() {
  const [phase, setPhase] = useState("idle"); // idle | running | done | error
  const [traceEvents, setTraceEvents] = useState([]);
  const [brief, setBrief] = useState("");
  const [briefStructured, setBriefStructured] = useState([]);
  const [weather, setWeather] = useState(null);
  const [error, setError] = useState("");
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [defaultCity, setDefaultCity] = useState("");

  useEffect(() => {
    const loadProfile = async () => {
      if (!user) {
        setDefaultCity("");
        return;
      }
      try {
        const { data, error } = await supabase
          .from('profiles')
          .select('city')
          .eq('user_id', user.id)
          .single();
        if (!error && data) {
          setDefaultCity(data.city || "");
        }
      } catch (e) {
        // ignore
      }
    };
    loadProfile();
  }, [user]);

  const API_BASE = import.meta.env.VITE_API_URL?.replace(/\/$/, "") || "";

  const runBrief = async ({ city, interests, focusToday }) => {
    setPhase("running");
    setTraceEvents([]);
    setBrief("");
    setBriefStructured([]);
    setError("");

    try {
      const headers = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`${API_BASE}/brief`, {
        method: "POST",
        headers,
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
              if (event.type === "tool_result" && event.tool === "get_weather") {
                setWeather(event.result || null);
              }
              } else if (event.type === "brief_structured") {
                setBriefStructured(event.items || []);
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
    setBriefStructured([]);
    setWeather(null);
    setError("");
  };

  return (
    <div className="app">
      <div className="bg-visuals" aria-hidden="true">
        <div className="bg-glow" />
        <div className="bg-grid" />
      </div>
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
        {!user ? (
          <section className="auth-stage">
            <Auth onUser={(u, t) => { setUser(u); setToken(t); }} variant="landing" />
          </section>
        ) : (
          <>
            <div className="auth-toolbar">
              <Auth onUser={(u, t) => { setUser(u); setToken(t); }} user={user} variant="toolbar" />
            </div>
            {!defaultCity && token && (
              <ProfileCity token={token} onSaved={(c) => setDefaultCity(c)} />
            )}
            {phase === "idle" && <BriefForm onSubmit={runBrief} defaultCity={defaultCity} />}

            {(phase === "running" || phase === "done") && (
              <div className="workspace">
                <AgentTrace events={traceEvents} isRunning={phase === "running"} />
                {brief && <BriefOutput content={brief} structured={briefStructured} weather={weather} onReset={reset} />}
              </div>
            )}
          </>
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
