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

  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const dateStr = now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });

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
            <div className="brief-weather-summary">{weather.summary || `${weather.city || ''} ${weather.temp_c ? weather.temp_c + '°C' : ''} ${weather.condition || ''}`}</div>
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
