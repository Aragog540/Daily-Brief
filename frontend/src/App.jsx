import { useState, useEffect } from "react";
import GoogleLogin from "./components/GoogleLogin";
import SettingsPanel from "./components/SettingsPanel";
import BriefOutput from "./components/BriefOutput";
import MadeBy from "./components/MadeBy";
import "./index.css";

export default function App() {
  const [email, setEmail] = useState(() => localStorage.getItem("vartaai-user-email") || "");
  const [view, setView] = useState("dashboard"); // dashboard | settings | login
  const [phase, setPhase] = useState("idle"); // idle | running | done | error
  const [digest, setDigest] = useState(null);
  const [error, setError] = useState("");
  const [profile, setProfile] = useState(null);
  const [focusToday, setFocusToday] = useState("");

  const apiBase = import.meta.env.VITE_API_URL || "";

  // 1. Process Google OAuth Redirect Callback parameter
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const emailParam = params.get("email");
    if (emailParam) {
      localStorage.setItem("vartaai-user-email", emailParam);
      setEmail(emailParam);
      // Clean query params from URL
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  // 2. Determine initial view gating
  useEffect(() => {
    if (!email) {
      setView("login");
    } else {
      setView("dashboard");
      // Fetch user profile info to check if they need to setup city
      const checkProfile = async () => {
        try {
          const res = await fetch(`${apiBase}/settings?email=${encodeURIComponent(email)}`);
          if (res.ok) {
            const data = await res.json();
            setProfile(data);
            if (!data.city) {
              // Redirect to settings for first setup
              setView("settings");
            }
          } else {
            // User entry doesn't exist yet, redirect to settings to initialize
            setView("settings");
          }
        } catch (e) {
          console.error("Error checking profile:", e);
        }
      };
      checkProfile();
    }
  }, [email, apiBase]);

  const handleLogout = () => {
    localStorage.removeItem("vartaai-user-email");
    setEmail("");
    setDigest(null);
    setPhase("idle");
    setView("login");
  };

  const handleGenerateDigest = async () => {
    setPhase("running");
    setError("");
    setDigest(null);
    try {
      const res = await fetch(`${apiBase}/brief`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          focus_today: focusToday.trim(),
        }),
      });

      if (res.status === 401) {
        throw new Error("Google access token has expired or is invalid. Please sign out and sign in again.");
      }
      if (!res.ok) {
        throw new Error(`Server error: ${res.status}`);
      }

      const data = await res.json();
      setDigest(data);
      setPhase("done");
    } catch (e) {
      setError(e.message || "Something went wrong.");
      setPhase("error");
    }
  };

  const reset = () => {
    setPhase("idle");
    setDigest(null);
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
            <span className="logo-text">Varta AI</span>
          </div>
          <p className="tagline">Your morning newspaper intelligence</p>
          {email && (
            <div className="header-actions">
              <span className="user-email-badge">{email}</span>
              <button className="btn muted" onClick={handleLogout}>
                Sign Out
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="main">
        {view === "login" && <GoogleLogin />}

        {view === "settings" && (
          <SettingsPanel
            email={email}
            onSaved={(p) => {
              setProfile(p);
              setView("dashboard");
            }}
            onClose={profile?.city ? () => setView("dashboard") : null}
          />
        )}

        {view === "dashboard" && (
          <>
            {phase === "idle" && (
              <div className="dashboard-runform form-card">
                <div className="form-header">
                  <h1 className="form-title">The Daily Chronicle</h1>
                  <p className="form-sub">Generate your bespoke daily newspaper print instantly.</p>
                </div>

                {profile && (
                  <div className="dashboard-profile-summary">
                    <span className="summary-badge">📍 {profile.city}</span>
                    {profile.interests?.map((i) => (
                      <span key={i} className="summary-badge interest">
                        #{i}
                      </span>
                    ))}
                  </div>
                )}

                <div className="field">
                  <label className="label">
                    Focus of the Day <span className="label-hint">(optional)</span>
                  </label>
                  <input
                    className="input"
                    type="text"
                    placeholder="e.g. key meetings, core tasks, presentation prep..."
                    value={focusToday}
                    onChange={(e) => setFocusToday(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleGenerateDigest()}
                  />
                </div>

                <div className="dashboard-actions">
                  <button className="btn-primary" onClick={handleGenerateDigest}>
                    <span>Generate Chronicle</span>
                    <span className="btn-arrow">→</span>
                  </button>
                  <button className="btn muted" onClick={() => setView("settings")}>
                    Chronicle Settings
                  </button>
                </div>
              </div>
            )}

            {phase === "running" && (
              <div className="newspaper-loading-screen">
                <div className="spinner" />
                <h2>Printing Your Morning Edition...</h2>
                <p>Fetching forecast, calendar docket, and correspondence from Google.</p>
              </div>
            )}

            {phase === "done" && (
              <BriefOutput
                digest={digest}
                onReset={reset}
                onOpenSettings={() => setView("settings")}
              />
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
          </>
        )}
      </main>

      <footer className="footer">
        <p>Powered by MPSB Studios</p>
      </footer>
      <MadeBy />
    </div>
  );
}
