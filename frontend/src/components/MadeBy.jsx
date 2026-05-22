import React from "react";

export default function MadeBy({ githubUser = "Aragog540", name = "Made by Swaroop" }) {
  const avatar = `https://github.com/${githubUser}.png`;
  return (
    <div className="madeby-card" aria-hidden="false">
      <div className="madeby-inner">
        <img className="madeby-avatar" src={avatar} alt={`${githubUser} avatar`} />
        <div className="madeby-meta">
          <div className="madeby-name">Made by</div>
          <div className="madeby-name-strong">Swaroop</div>
          <div className="madeby-links">
            <a href="https://github.com/Aragog540" target="_blank" rel="noopener noreferrer">GitHub</a>
            <a href="https://www.linkedin.com/in/swaroop-bhowmik-8907b52a0/" target="_blank" rel="noopener noreferrer">LinkedIn</a>
            <a href="https://www.instagram.com/_.swar.oop._/" target="_blank" rel="noopener noreferrer">Instagram</a>
          </div>
        </div>
      </div>
    </div>
  );
}
