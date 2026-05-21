import { useEffect, useState } from 'react';
import { supabase } from '../supabaseClient';

export default function Auth({ onUser }) {
  const [email, setEmail] = useState('');
  const [msg, setMsg] = useState('');

  useEffect(() => {
    const init = async () => {
      const { data } = await supabase.auth.getSession();
      if (data?.session) {
        onUser(data.session.user, data.session.access_token);
      }
      supabase.auth.onAuthStateChange((event, session) => {
        if (session?.user) {
          onUser(session.user, session.access_token);
        } else {
          onUser(null, null);
        }
      });
    };
    init();
  }, []);

  const signIn = async () => {
    setMsg('');
    if (!email) return setMsg('Enter your email.');
    const { error } = await supabase.auth.signInWithOtp({ email });
    if (error) setMsg(error.message);
    else setMsg('Magic link sent — check your email.');
  };

  const signOut = async () => {
    await supabase.auth.signOut();
    onUser(null, null);
  };

  return (
    <div className="auth">
      <div className="auth-inner">
        <input
          className="input"
          type="email"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <button className="btn" onClick={signIn}>Sign in</button>
        <button className="btn muted" onClick={signOut}>Sign out</button>
        {msg && <p className="auth-msg">{msg}</p>}
      </div>
    </div>
  );
}
