const TOOL_META = {
  get_weather: { icon: "🌤", label: "Checking weather" },
  search_news: { icon: "🔍", label: "Searching news" },
  get_day_context: { icon: "📅", label: "Reading the date" },
};

function TraceEvent({ event }) {
  if (event.type === "tool_call") {
    const meta = TOOL_META[event.tool] || { icon: "⚙", label: event.tool };
    const detail =
      event.args.city ||
      event.args.topic ||
      event.args.date_str ||
      "";
    return (
      <div className="trace-row trace-call">
        <span className="trace-icon">{meta.icon}</span>
        <span className="trace-text">
          {meta.label}
          {detail && <span className="trace-detail"> · {detail}</span>}
        </span>
        <span className="trace-spinner" />
      </div>
    );
  }

  if (event.type === "tool_result") {
    const meta = TOOL_META[event.tool] || { icon: "✓", label: event.tool };
    const r = event.result;
    let summary = "Done";

    if (event.tool === "get_weather" && r.temp_c !== undefined) {
      summary = `${r.temp_c}°C, ${r.condition} in ${r.city}`;
    } else if (event.tool === "search_news" && r.articles) {
      summary = `${r.articles.length} articles on "${r.topic}"`;
    } else if (event.tool === "get_day_context" && r.weekday) {
      summary = `${r.weekday}, ${r.date}`;
    } else if (r.error) {
      summary = `Error: ${r.error}`;
    }

    return (
      <div className="trace-row trace-result">
        <span className="trace-icon">✓</span>
        <span className="trace-text trace-done">{summary}</span>
      </div>
    );
  }

  return null;
}

export default function AgentTrace({ events, isRunning }) {
  // Deduplicate: show only the last result for each tool call
  // but show call + result pairs
  const rows = [];
  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    // If this is a tool_call and the NEXT event is its result, skip the spinner version
    if (
      e.type === "tool_call" &&
      events[i + 1]?.type === "tool_result" &&
      events[i + 1]?.tool === e.tool
    ) {
      rows.push(<TraceEvent key={i} event={events[i + 1]} />);
      i++; // skip the next result since we just rendered it
    } else {
      rows.push(<TraceEvent key={i} event={e} />);
    }
  }

  return (
    <div className="trace-panel">
      <div className="trace-header">
        <span className="trace-title">Agent trace</span>
        {isRunning && <span className="trace-running-badge">running</span>}
      </div>
      <div className="trace-body">{rows}</div>
      {isRunning && events.length === 0 && (
        <div className="trace-row">
          <span className="trace-spinner" />
          <span className="trace-text trace-muted">Starting agent…</span>
        </div>
      )}
    </div>
  );
}
