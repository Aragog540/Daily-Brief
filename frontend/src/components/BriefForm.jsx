import { useState } from "react";

function getGreetingByHour(hour) {
  if (hour >= 5 && hour < 12) return "Good morning.";
  if (hour >= 12 && hour < 17) return "Good afternoon.";
  if (hour >= 17 && hour < 20) return "Good evening.";
  return "Good evening.";
}

export default function BriefForm({ onSubmit, profile }) {
  const [focusToday, setFocusToday] = useState("");
  const [err, setErr] = useState("");
  const greeting = getGreetingByHour(new Date().getHours());

  const handleSubmit = () => {
    setErr("");
    onSubmit({ focusToday: focusToday.trim() });
  };

  return (
    <div className="form-card">
      <div className="form-header">
        <h1 className="form-title">{greeting}</h1>
        <p className="form-sub">Tell me about your day. I'll handle the rest.</p>
      </div>

      {profile?.city && (
        <div className="profile-chip">
          <span>Saved city</span>
          <strong>{profile.city}</strong>
        </div>
      )}

      {profile?.interests?.length > 0 && (
        <div className="profile-chip-list">
          <span>Saved interests</span>
          <div className="profile-chip-row">
            {profile.interests.slice(0, 5).map((item) => (
              <span className="profile-chip-item" key={item}>{item}</span>
            ))}
          </div>
        </div>
      )}

      <div className="field">
        <label className="label">
          What are you focused on today? <span className="label-hint">(optional)</span>
        </label>
        <input
          className="input"
          type="text"
          placeholder="e.g. finishing my portfolio, a big presentation..."
          value={focusToday}
          onChange={(e) => setFocusToday(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        />
      </div>

      {err && <p className="form-err">{err}</p>}

      <button className="btn-primary" onClick={handleSubmit}>
        <span>Run my brief</span>
        <span className="btn-arrow">→</span>
      </button>
    </div>
  );
}
