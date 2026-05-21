import { useEffect, useState } from 'react';
import { supabase } from '../supabaseClient';

export default function Auth({ onUser, user, variant = 'landing' }) {
  const [email, setEmail] = useState('');
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
    const redirectTo = import.meta.env.VITE_SITE_URL || window.location.origin;
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: redirectTo,
      },
    });
    if (error) setMsg(error.message);
    else setMsg('Magic link sent — check your email.');
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
            <h2 className="auth-title">Sign up or sign in with a magic link</h2>
            <p className="auth-copy">Use your email to create an account. The same link also signs you back in later.</p>
          </>
        )}
        <input
          className="input"
          type="email"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <button className="btn" onClick={signIn}>{variant === 'landing' ? 'Send magic link' : 'Sign in'}</button>
        {user && <button className="btn muted" onClick={signOut}>Sign out</button>}
        {msg && <p className="auth-msg">{msg}</p>}
      </div>
    </div>
  );
}
