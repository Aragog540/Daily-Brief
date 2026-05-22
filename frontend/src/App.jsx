import { useState, useEffect } from "react";
import BriefForm from "./components/BriefForm";
import AgentTrace from "./components/AgentTrace";
import BriefOutput from "./components/BriefOutput";
import "./index.css";
import Auth from "./components/Auth";
import { supabase } from "./supabaseClient";
import BriefHistory from "./components/BriefHistory";

function parseInterests(value) {
  if (Array.isArray(value)) return value.filter((item) => typeof item === "string" && item.trim()).map((item) => item.trim());
  if (typeof value === "string") return value.split(",").map((item) => item.trim()).filter(Boolean);
  return [];
}

function loadHistory(key) {
  if (!key) return [];
  try {
    const raw = localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export default function App() {
  const [phase, setPhase] = useState("idle"); // idle | running | done | error
  const [traceEvents, setTraceEvents] = useState([]);
  const [brief, setBrief] = useState("");
  const [briefStructured, setBriefStructured] = useState([]);
  const [weather, setWeather] = useState(null);
  const [error, setError] = useState("");
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [profile, setProfile] = useState({ city: "", interests: [] });
  const [history, setHistory] = useState([]);
  const [activeHistoryId, setActiveHistoryId] = useState(null);
  const historyKey = user?.id ? `dailybrief-history-${user.id}` : null;

  useEffect(() => {
    const loadProfile = async () => {
      if (!user) {
        setProfile({ city: "", interests: [] });
        return;
      }
      try {
        const metadata = user.user_metadata || user.raw_user_meta_data || {};
        const interests = parseInterests(metadata.interests || metadata.preferred_interests);
        let city = metadata.city || metadata.preferred_city || "";
        const { data, error } = await supabase
          .from('profiles')
          .select('city')
          .eq('user_id', user.id)
          .single();
        if (!city && !error && data) {
          city = data.city || "";
        }
        setProfile({ city, interests });
      } catch (e) {
        const metadata = user.user_metadata || user.raw_user_meta_data || {};
        setProfile({
          city: metadata.city || metadata.preferred_city || "",
          interests: parseInterests(metadata.interests || metadata.preferred_interests),
        });
      }
    };
    loadProfile();
  }, [user]);

  useEffect(() => {
    if (!historyKey) {
      setHistory([]);
      setActiveHistoryId(null);
      return;
    }
    setHistory(loadHistory(historyKey));
    setActiveHistoryId(null);
  }, [historyKey]);

  useEffect(() => {
    if (!historyKey) return;
    try {
      localStorage.setItem(historyKey, JSON.stringify(history.slice(0, 12)));
    } catch {
      // ignore storage errors
    }
  }, [history, historyKey]);

  const API_BASE = import.meta.env.VITE_API_URL?.replace(/\/$/, "") || "";

  const runBrief = async ({ focusToday }) => {
    setPhase("running");
    setTraceEvents([]);
    setBrief("");
    setBriefStructured([]);
    setError("");
    setActiveHistoryId(null);

    const savedCity = profile.city || "";
    const savedInterests = profile.interests || [];
    let latestBrief = "";
    let latestStructured = [];
    let latestWeather = null;

    try {
      const headers = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`${API_BASE}/brief`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          city: savedCity,
          interests: savedInterests,
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
                latestWeather = event.result || null;
                setWeather(latestWeather);
              }
              } else if (event.type === "brief_structured") {
                latestStructured = event.items || [];
                setBriefStructured(latestStructured);
              } else if (event.type === "brief") {
                latestBrief = event.content || "";
                setBrief(latestBrief);
                setPhase("done");
            } else if (event.type === "error") {
              setError(event.message);
              setPhase("error");
            } else if (event.type === "done") {
              if (latestBrief) {
                const entry = {
                  id: crypto.randomUUID(),
                  createdAt: new Date().toISOString(),
                  city: savedCity,
                  interests: savedInterests,
                  focusToday: focusToday || "",
                  content: latestBrief,
                  structured: latestStructured,
                  weather: latestWeather,
                };
                setHistory((prev) => [entry, ...prev.filter((item) => item.content !== latestBrief)].slice(0, 12));
                setActiveHistoryId(entry.id);
              }
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

  const handleLogout = async () => {
    await supabase.auth.signOut();
    setUser(null);
    setToken(null);
    setProfile({ city: "", interests: [] });
    setHistory([]);
    setActiveHistoryId(null);
    reset();
  };

  const handleSelectHistory = (entry) => {
    setBrief(entry.content || "");
    setBriefStructured(entry.structured || []);
    setWeather(entry.weather || null);
    setPhase("done");
    setError("");
    setTraceEvents([]);
    setActiveHistoryId(entry.id);
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
          {user && (
            <button className="btn muted header-logout" onClick={handleLogout}>
              Logout
            </button>
          )}
        </div>
      </header>

      <main className="main">
        {!user ? (
          <section className="auth-stage">
            <Auth onUser={(u, t) => { setUser(u); setToken(t); }} variant="landing" />
          </section>
        ) : (
          <div className="workspace-layout">
            <aside className="history-shell">
              <BriefHistory
                entries={history}
                activeId={activeHistoryId}
                onSelect={handleSelectHistory}
              />
            </aside>

            <section className="workspace-main">
              {phase === "idle" && (
                <BriefForm onSubmit={runBrief} profile={profile} />
              )}

              {(phase === "running" || phase === "done") && (
                <div className="workspace">
                  <AgentTrace events={traceEvents} isRunning={phase === "running"} />
                  {brief && <BriefOutput content={brief} structured={briefStructured} weather={weather} onReset={reset} />}
                </div>
              )}
            </section>
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
