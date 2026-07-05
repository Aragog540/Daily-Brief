import { useState, useEffect } from "react";

export default function SettingsPanel({ email, onSaved, onClose }) {
  const [city, setCity] = useState("");
  const [interests, setInterests] = useState("");
  const [deliveryTime, setDeliveryTime] = useState("07:00");
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const apiBase = import.meta.env.VITE_API_URL || "";

  useEffect(() => {
    const fetchSettings = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${apiBase}/settings?email=${encodeURIComponent(email)}`);
        if (res.ok) {
          const data = await res.json();
          setCity(data.city || "");
          setInterests(data.interests?.join(", ") || "");
          setDeliveryTime(data.delivery_time || "07:00");
          setTimezone(data.timezone || "Asia/Kolkata");
          setEnabled(data.enabled ?? true);
        }
      } catch (e) {
        console.error("Failed to load user settings:", e);
      } finally {
        setLoading(false);
      }
    };
    fetchSettings();
  }, [email, apiBase]);

  const handleSave = async () => {
    setErr("");
    setMsg("");
    if (!city.trim()) {
      setErr("Please enter a city for weather alerts.");
      return;
    }
    setLoading(true);
    try {
      const interestsArray = interests
        .split(",")
        .map((i) => i.trim())
        .filter(Boolean);

      const res = await fetch(`${apiBase}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          city: city.trim(),
          interests: interestsArray,
          delivery_time: deliveryTime,
          timezone,
          enabled,
        }),
      });

      if (!res.ok) throw new Error("Failed to save settings.");
      setMsg("Chronicle settings updated successfully.");
      if (onSaved) {
        onSaved({ city: city.trim(), interests: interestsArray, deliveryTime, timezone, enabled });
      }
    } catch (e) {
      setErr(e.message || "Save failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="settings-panel form-card">
      <div className="settings-header">
        <h2 className="settings-title">Chronicle Settings</h2>
        <p className="settings-sub">Configure your customized daily morning newspaper digest.</p>
      </div>

      {loading && <p className="settings-loading">Loading settings...</p>}

      <div className="field">
        <label className="label">Home City (for weather & alerts)</label>
        <input
          className="input"
          type="text"
          value={city}
          onChange={(e) => setCity(e.target.value)}
          placeholder="e.g. Vadodara, Mumbai..."
        />
      </div>

      <div className="field">
        <label className="label">Topics of Interest (comma-separated)</label>
        <input
          className="input"
          type="text"
          value={interests}
          onChange={(e) => setInterests(e.target.value)}
          placeholder="e.g. Technology, Startups, Indian Politics..."
        />
      </div>

      <div className="settings-row">
        <div className="field half">
          <label className="label">Delivery Time</label>
          <input
            className="input"
            type="time"
            value={deliveryTime}
            onChange={(e) => setDeliveryTime(e.target.value)}
          />
        </div>

        <div className="field half">
          <label className="label">Timezone</label>
          <select
            className="input select-input"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
          >
            <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
            <option value="America/New_York">America/New_York (EST)</option>
            <option value="Europe/London">Europe/London (GMT)</option>
            <option value="Asia/Singapore">Asia/Singapore (SGT)</option>
          </select>
        </div>
      </div>

      <div className="field checkbox-field">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          <span className="checkbox-text">Email me my morning Chronicle at the delivery time</span>
        </label>
      </div>

      {err && <p className="form-err">{err}</p>}
      {msg && <p className="form-success">{msg}</p>}

      <div className="settings-actions">
        <button className="btn-primary" onClick={handleSave} disabled={loading}>
          Save Settings
        </button>
        {onClose && (
          <button className="btn muted" onClick={onClose}>
            Back to Dashboard
          </button>
        )}
      </div>
    </div>
  );
}
