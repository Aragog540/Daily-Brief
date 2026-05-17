export default function BriefOutput({ content, structured, weather, onReset }) {
  // Simple markdown-ish renderer: bullet lines and normal lines
  const lines = content.split("\n").filter((l) => l.trim());

  const renderLine = (line, idx) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("- ") || trimmed.startsWith("• ")) {
      return (
        <li key={idx} className="brief-bullet">
          {trimmed.slice(2)}
        </li>
      );
    }
    if (trimmed.startsWith("**") && trimmed.endsWith("**")) {
      return (
        <p key={idx} className="brief-bold">
          {trimmed.slice(2, -2)}
        </p>
      );
    }
    return (
      <p key={idx} className="brief-para">
        {trimmed}
      </p>
    );
  };

  // Group bullets into <ul>
  const rendered = [];
  let bulletBuffer = [];

  const flushBullets = () => {
    if (bulletBuffer.length) {
      rendered.push(<ul key={`ul-${rendered.length}`} className="brief-list">{bulletBuffer}</ul>);
      bulletBuffer = [];
    }
  };

  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("- ") || trimmed.startsWith("• ")) {
      bulletBuffer.push(
        <li key={idx} className="brief-bullet">
          {trimmed.slice(2)}
        </li>
      );
    } else {
      flushBullets();
      rendered.push(renderLine(line, idx));
    }
  });
  flushBullets();

  // Prefer weather-provided current_time for the generated timestamp (falls back to local now)
  let localDt = null;
  if (weather && weather.current_time) {
    // ISO string from backend; construct Date. Browser will interpret missing offset as local.
    localDt = new Date(weather.current_time);
    if (isNaN(localDt.getTime())) localDt = null;
  }
  if (!localDt) localDt = new Date();
  const timeStr = localDt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const dateStr = localDt.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });

  return (
    <div className="brief-card">
      <div className="brief-meta">
        <span className="brief-date">{dateStr}</span>
        <span className="brief-time">Generated at {timeStr}</span>
      </div>

      <div className="brief-divider" />

      <div className="brief-content">
        {weather ? (
          <div className="brief-weather">
            {/* time-aware summary: if night, prefer Tonight/Tomorrow phrasing */}
            {(() => {
              const dt = localDt;
              const hour = dt.getHours();
              const max = weather.max_temp_c;
              const min = weather.min_temp_c;
              if ((hour < 6 || hour >= 20) && min != null && max != null) {
                return (
                  <div className="brief-weather-summary">{`Tonight: lows around ${min}°C. Tomorrow expect highs near ${max}°C.`}</div>
                );
              }
              // default: show current temp + short condition, or summary
              const simple = weather.summary || `${weather.city || ''} ${weather.temp_c ? weather.temp_c + '°C' : ''} ${weather.condition || ''}`;
              return <div className="brief-weather-summary">{simple}</div>;
            })()}
            {weather.advice && weather.advice.length > 0 && (
              <ul className="brief-weather-advice">
                {weather.advice.map((a, idx) => (
                  <li key={idx} className="brief-advice">{a}</li>
                ))}
              </ul>
            )}
          </div>
        ) : null}

        {structured && structured.length > 0 ? (
          <ol className="brief-ol">
            {structured.map((it, i) => (
              <li key={i} className="brief-item">
                <span className="brief-title">{it.title}</span>
                <a href={it.url} target="_blank" rel="noopener noreferrer" className="brief-link-mini">🔗</a>
                <div className="brief-src">{it.source} {it.published ? `· ${it.published}` : ""}</div>
              </li>
            ))}
          </ol>
        ) : (
          rendered
        )}
      </div>

      <div className="brief-divider" />

      <div className="brief-footer">
        <button className="btn-reset" onClick={onReset}>
          ← New brief
        </button>
        <button
          className="btn-copy"
          onClick={() => navigator.clipboard?.writeText(content)}
        >
          Copy text
        </button>
      </div>
    </div>
  );
}
