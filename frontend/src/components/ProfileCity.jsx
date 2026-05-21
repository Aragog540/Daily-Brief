import { useState } from 'react';

export default function ProfileCity({ token, onSaved }) {
  const [city, setCity] = useState('');
  const [msg, setMsg] = useState('');

  const save = async () => {
    setMsg('');
    if (!city.trim()) return setMsg('Enter a city');
    try {
      const res = await fetch((import.meta.env.VITE_API_URL || '') + '/profile', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ city: city.trim() }),
      });
      if (!res.ok) throw new Error('Failed to save');
      onSaved(city.trim());
    } catch (e) {
      setMsg(e.message || 'Save failed');
    }
  };

  return (
    <div className="profile-city">
      <p>Please set your city to receive localized briefs.</p>
      <input className="input" value={city} onChange={(e) => setCity(e.target.value)} placeholder="e.g. Ahmedabad" />
      <button className="btn" onClick={save}>Save</button>
      {msg && <div className="auth-msg">{msg}</div>}
    </div>
  );
}
