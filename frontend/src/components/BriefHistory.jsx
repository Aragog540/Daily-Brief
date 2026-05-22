function formatStamp(value) {
  try {
    return new Date(value).toLocaleString([], {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return value;
  }
}

export default function BriefHistory({ entries = [], activeId, onSelect }) {
  return (
    <div className="history-panel">
      <div className="history-head">
        <p className="history-kicker">History</p>
        <h2 className="history-title">Recent briefs</h2>
        <p className="history-copy">Open a past brief anytime. Your recent runs stay on this device.</p>
      </div>

      <div className="history-list">
        {entries.length === 0 ? (
          <div className="history-empty">
            <span className="history-empty-mark">◌</span>
            <p>No briefs yet.</p>
            <small>Generate one and it will appear here.</small>
          </div>
        ) : (
          entries.map((entry) => {
            const firstHeadline = entry.structured?.[0]?.title || entry.content?.split('\n').find(Boolean) || 'Saved brief';
            return (
              <button
                key={entry.id}
                className={`history-item ${activeId === entry.id ? 'history-item-active' : ''}`}
                onClick={() => onSelect(entry)}
              >
                <span className="history-item-date">{formatStamp(entry.createdAt)}</span>
                <span className="history-item-title">{firstHeadline}</span>
                {entry.focusToday && <span className="history-item-focus">{entry.focusToday}</span>}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}