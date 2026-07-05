import React from "react";

export default function BriefOutput({ digest, onReset, onOpenSettings }) {
  if (!digest) return null;

  const dateStr = new Date().toLocaleDateString([], {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  const timeStr = new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  // Handle copying the newspaper content as text
  const handleCopyText = () => {
    let copyText = `THE DAILY CHRONICLE\n${dateStr}\n\n`;
    
    if (digest.greeting) copyText += `${digest.greeting}\n\n`;
    if (digest.advisory) copyText += `ADVISORY: ${digest.advisory}\n\n`;
    
    copyText += `--- THE DAILY DOCKET (Calendar) ---\n`;
    if (digest.calendar_editorial) copyText += `${digest.calendar_editorial}\n`;
    digest.calendar_items?.forEach(item => {
      copyText += `- [${item.time}] ${item.title}${item.location ? ` (${item.location})` : ""}\n`;
    });
    copyText += `\n`;

    copyText += `--- CORRESPONDENCE (Inbox) ---\n`;
    if (digest.inbox_editorial) copyText += `${digest.inbox_editorial}\n`;
    digest.inbox_items?.forEach(item => {
      copyText += `- From: ${item.from} | Subject: ${item.subject} | Summary: ${item.summary}\n`;
    });
    copyText += `\n`;

    copyText += `--- CHRONICLES & HEADLINES ---\n`;
    digest.news_columns?.forEach(col => {
      copyText += `[${col.topic}]\n`;
      col.articles?.forEach(art => {
        copyText += `- ${art.title} (Source: ${art.source})\n  ${art.summary}\n`;
      });
    });
    copyText += `\n`;

    if (digest.thought_of_the_day) {
      copyText += `Thought for the day: "${digest.thought_of_the_day}"\n`;
    }

    navigator.clipboard?.writeText(copyText);
    alert("Newspaper content copied to clipboard!");
  };

  return (
    <div className="newspaper-wrapper">
      <div className="newspaper-controls">
        <button className="btn reset-btn" onClick={onReset}>
          ← New Edition
        </button>
        <button className="btn settings-btn" onClick={onOpenSettings}>
          Chronicle Settings
        </button>
        <button className="btn copy-btn" onClick={handleCopyText}>
          Copy Print Text
        </button>
      </div>

      <div className="newspaper-sheet">
        {/* Header Title Block */}
        <header className="newspaper-header">
          <div className="header-top">
            <span className="volume-label">Vol. II · No. 24</span>
            <span className="price-label">Two Cents</span>
          </div>
          <h1 className="chronicle-title">The Daily Chronicle</h1>
          <div className="header-meta">
            <span className="meta-date">{dateStr}</span>
            <span className="meta-edition">Morning Edition</span>
            <span className="meta-time">Generated at {timeStr}</span>
          </div>
        </header>

        {/* Warning Weather Advisory Banner */}
        {digest.advisory && (
          <div className="newspaper-advisory">
            <span className="advisory-kicker">WEATHER ALERT: </span>
            <span className="advisory-text">{digest.advisory}</span>
          </div>
        )}

        {/* Greeting Column */}
        {digest.greeting && (
          <section className="newspaper-greeting">
            <p className="greeting-text italic-editorial">
              {digest.greeting}
            </p>
          </section>
        )}

        {/* Two-Column Grid: Calendar Docket vs Correspondence */}
        <div className="newspaper-grid two-column">
          {/* Column 1: The Daily Docket */}
          <div className="newspaper-col column-left">
            <h2 className="section-header">The Daily Docket</h2>
            {digest.calendar_editorial && (
              <p className="col-editorial">{digest.calendar_editorial}</p>
            )}
            
            <div className="events-list">
              {digest.calendar_items && digest.calendar_items.length > 0 ? (
                digest.calendar_items.map((item, idx) => (
                  <div key={idx} className="newspaper-event-item">
                    <span className="event-item-time">{item.time}</span>
                    <div className="event-item-details">
                      <strong className="event-item-title">{item.title}</strong>
                      {item.location && (
                        <span className="event-item-loc">📍 {item.location}</span>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <p className="no-items-text">Your schedule for today is clear.</p>
              )}
            </div>
          </div>

          {/* Column 2: Inbox Correspondence */}
          <div className="newspaper-col column-right">
            <h2 className="section-header">Correspondence</h2>
            {digest.inbox_editorial && (
              <p className="col-editorial">{digest.inbox_editorial}</p>
            )}

            <div className="inbox-list">
              {digest.inbox_items && digest.inbox_items.length > 0 ? (
                digest.inbox_items.map((item, idx) => (
                  <div key={idx} className="newspaper-email-item">
                    <div className="email-item-meta">
                      <span className="email-item-from">From: {item.from}</span>
                      <strong className="email-item-subject">{item.subject}</strong>
                    </div>
                    <p className="email-item-summary">{item.summary}</p>
                  </div>
                ))
              ) : (
                <p className="no-items-text">No recent correspondence to summarize.</p>
              )}
            </div>
          </div>
        </div>

        {/* Global/Curated News Section */}
        {digest.news_columns && digest.news_columns.length > 0 && (
          <section className="newspaper-news-section">
            <h2 className="section-header center-header">Chronicles & Bulletins</h2>
            <div className="newspaper-grid news-columns-grid">
              {digest.news_columns.map((col, idx) => (
                <div key={idx} className="news-column-article">
                  <h3 className="column-topic-title">{col.topic}</h3>
                  {col.articles && col.articles.length > 0 ? (
                    col.articles.map((art, aIdx) => (
                      <div key={aIdx} className="news-article-item">
                        <h4 className="news-article-title">{art.title}</h4>
                        <span className="news-article-source">Source: {art.source}</span>
                        <p className="news-article-summary">{art.summary}</p>
                      </div>
                    ))
                  ) : (
                    <p className="no-items-text">No articles found on this topic today.</p>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Footer/Editorial Thought */}
        {digest.thought_of_the_day && (
          <footer className="newspaper-footer">
            <p className="thought-text">
              "{digest.thought_of_the_day}"
            </p>
            <div className="editorial-signature">
              <span>— The Editorial Board</span>
            </div>
            <div className="footer-copyright">
              <small>Delivered daily to your inbox at 7 AM. Printed via Varta AI.</small>
            </div>
          </footer>
        )}
      </div>
    </div>
  );
}
