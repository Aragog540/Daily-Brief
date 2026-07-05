import { useState } from "react";

export default function GoogleLogin() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async () => {
    setLoading(true);
    setError("");
    try {
      const apiBase = import.meta.env.VITE_API_URL || "";
      const res = await fetch(`${apiBase}/auth/login`);
      if (!res.ok) throw new Error("Could not initialize Google OAuth flow.");
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      } else {
        throw new Error("Invalid response from server.");
      }
    } catch (e) {
      setError(e.message || "Something went wrong.");
      setLoading(false);
    }
  };

  return (
    <div className="auth-inner newspaper-login">
      <div className="newspaper-brand">
        <span className="newspaper-kicker">Est. 2026</span>
        <h1 className="newspaper-brand-title">The Daily Chronicle</h1>
        <div className="newspaper-brand-divider" />
        <p className="newspaper-brand-tagline">
          Your Personal Morning Edition — Powered by AI
        </p>
      </div>

      <div className="newspaper-pitch">
        <p>
          Welcome to your morning intelligence. The Chronicle fetches your
          upcoming meetings from <strong>Google Calendar</strong>, scans your
          <strong> Gmail</strong> for critical updates, merges local weather
          alerts, and curates local news into a retro multi-column layout.
        </p>
        <p>
          Delivered directly to your inbox at <strong>7:00 AM</strong> daily, or
          generated live on-demand.
        </p>
      </div>

      <button className="btn-primary google-login-btn" onClick={handleLogin} disabled={loading}>
        {loading ? (
          <span>Connecting to Google...</span>
        ) : (
          <>
            <span className="google-icon">G</span>
            <span>Sign in with Google</span>
          </>
        )}
      </button>

      {error && <p className="form-err login-err">{error}</p>}
    </div>
  );
}
