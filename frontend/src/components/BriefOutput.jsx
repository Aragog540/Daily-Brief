export default function BriefOutput({ content, onReset }) {
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

      <div className="brief-content">{rendered}</div>

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
