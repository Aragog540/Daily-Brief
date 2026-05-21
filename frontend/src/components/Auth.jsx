import { useEffect, useState } from 'react';
import { supabase } from '../supabaseClient';

export default function Auth({ onUser, user, variant = 'landing' }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
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
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: import.meta.env.VITE_SITE_URL || window.location.origin,
      },
    });
    if (error) setMsg(error.message);
    else setMsg('Account created. You are signed in if email confirmation is disabled.');
  };

  const signOut = async () => {
    await supabase.auth.signOut();
    onUser(null, null);
  };

  return (
    <div className={`auth auth-${variant}`}>
      <div className="auth-inner">
        {variant === 'landing' && (
          <>
            <p className="auth-kicker">Create your personal brief</p>
            <h2 className="auth-title">Sign in once, stay signed in</h2>
            <p className="auth-copy">Use your email and password. Supabase keeps the session in the browser until you log out.</p>
          </>
        )}
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
        <div className="auth-actions">
          <button className="btn" onClick={signIn}>Sign in</button>
          <button className="btn muted" onClick={signUp}>Create account</button>
        </div>
        {user && <button className="btn muted" onClick={signOut}>Sign out</button>}
        {msg && <p className="auth-msg">{msg}</p>}
      </div>
    </div>
  );
}
