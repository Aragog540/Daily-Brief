import { useEffect, useState } from 'react';
import { supabase } from '../supabaseClient';

const INTEREST_OPTIONS = [
  'Technology', 'Science', 'Business', 'Sports', 'Politics',
  'AI & ML', 'Finance', 'Climate', 'India', 'Startups',
  'Cricket', 'Entertainment', 'Health', 'Space',
];

export default function Auth({ onUser, variant = 'landing' }) {
  const [mode, setMode] = useState('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [city, setCity] = useState('');
  const [interests, setInterests] = useState([]);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    let subscription;

    const init = async () => {
      const { data } = await supabase.auth.getSession();
      if (data?.session) {
        onUser(data.session.user, data.session.access_token);
      }
      const { data: { subscription: sub } } = supabase.auth.onAuthStateChange((event, session) => {
        if (session?.user) {
          onUser(session.user, session.access_token);
        } else {
          onUser(null, null);
        }
      });
      subscription = sub;
    };

    init();
    return () => subscription?.unsubscribe();
  }, []);

  const signIn = async () => {
    setMsg('');
    if (!email) return setMsg('Enter your email.');
    if (!password) return setMsg('Enter your password.');
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) setMsg(error.message);
  };

  const signUp = async () => {
    setMsg('');
    if (!email) return setMsg('Enter your email.');
    if (!password) return setMsg('Enter your password.');
    if (!city.trim()) return setMsg('Enter your preferred city.');
    if (interests.length === 0) return setMsg('Pick at least one interest.');
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: import.meta.env.VITE_SITE_URL || window.location.origin,
        data: {
          city: city.trim(),
          interests,
        },
      },
    });
    if (error) setMsg(error.message);
    else setMsg('Account created. You can sign in once email confirmation is complete.');
  };

  const toggleInterest = (item) => {
    setInterests((prev) => (
      prev.includes(item)
        ? prev.filter((current) => current !== item)
        : [...prev, item].slice(0, 5)
    ));
  };

  return (
    <div className={`auth auth-${variant}`}>
      <div className="auth-inner">
        {variant === 'landing' && (
          <>
            <p className="auth-kicker">Create your personal brief</p>
            <h2 className="auth-title">Sign in once, stay signed in</h2>
            <p className="auth-copy">Sign in once and the browser keeps your session until you log out.</p>
          </>
        )}

          <div className="auth-tabs">
            <button className={`auth-tab ${mode === 'signin' ? 'auth-tab-active' : ''}`} onClick={() => setMode('signin')}>Sign in</button>
            <button className={`auth-tab ${mode === 'signup' ? 'auth-tab-active' : ''}`} onClick={() => setMode('signup')}>Create account</button>
          </div>

          <input
            className="input"
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            className="input"
            type="password"
            placeholder="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          {mode === 'signup' && (
            <>
              <input
                className="input"
                type="text"
                placeholder="preferred city, e.g. Ahmedabad"
                value={city}
                onChange={(e) => setCity(e.target.value)}
              />

              <div className="auth-picklist">
                <div className="auth-label">Interests</div>
                <div className="pill-grid">
                  {INTEREST_OPTIONS.map((item) => (
                    <button
                      key={item}
                      className={`pill ${interests.includes(item) ? 'pill-active' : ''}`}
                      onClick={() => toggleInterest(item)}
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}

          <div className="auth-actions">
            {mode === 'signin' ? (
              <>
                <button className="btn" onClick={signIn}>Sign in</button>
                <button className="btn muted" onClick={() => setMode('signup')}>Need an account?</button>
              </>
            ) : (
              <>
                <button className="btn" onClick={signUp}>Create account</button>
                <button className="btn muted" onClick={() => setMode('signin')}>Back to sign in</button>
              </>
            )}
          </div>
        {msg && <p className="auth-msg">{msg}</p>}
      </div>
    </div>
  );
}
