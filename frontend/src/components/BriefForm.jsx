import { useState } from "react";

const INTEREST_OPTIONS = [
  "Technology", "Science", "Business", "Sports", "Politics",
  "AI & ML", "Finance", "Climate", "India", "Startups",
  "Cricket", "Entertainment", "Health", "Space",
];

export default function BriefForm({ onSubmit }) {
  const [city, setCity] = useState("");
  const [interests, setInterests] = useState([]);
  const [focusToday, setFocusToday] = useState("");
  const [err, setErr] = useState("");

  const toggleInterest = (i) => {
    setInterests((prev) =>
      prev.includes(i) ? prev.filter((x) => x !== i) : [...prev, i].slice(0, 3)
    );
  };

  const handleSubmit = () => {
    if (!city.trim()) return setErr("Enter your city.");
    if (interests.length === 0) return setErr("Pick at least one interest.");
    setErr("");
    onSubmit({ city: city.trim(), interests, focusToday: focusToday.trim() });
  };

  return (
    <div className="form-card">
      <div className="form-header">
        <h1 className="form-title">Good morning.</h1>
        <p className="form-sub">Tell me about your day. I'll handle the rest.</p>
      </div>

      <div className="field">
        <label className="label">Your city</label>
        <input
          className="input"
          type="text"
          placeholder="e.g. Ahmedabad"
          value={city}
          onChange={(e) => setCity(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        />
      </div>

      <div className="field">
        <label className="label">
          Interests <span className="label-hint">(pick up to 3)</span>
        </label>
        <div className="pill-grid">
          {INTEREST_OPTIONS.map((i) => (
            <button
              key={i}
              className={`pill ${interests.includes(i) ? "pill-active" : ""}`}
              onClick={() => toggleInterest(i)}
            >
              {i}
            </button>
          ))}
        </div>
      </div>

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
