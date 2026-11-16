import { FormEvent, useState } from "react";
import { supabase } from "../lib/supabase";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const [attesa, setAttesa] = useState(false);

  const entra = async (e: FormEvent) => {
    e.preventDefault();
    setAttesa(true); setMsg(null);
    const { error } = await supabase!.auth.signInWithPassword({ email, password });
    setAttesa(false);
    if (error) setMsg({ ok: false, t: error.message === "Invalid login credentials" ? "Email o password errate." : error.message });
  };
  const recupera = async () => {
    if (!email) return setMsg({ ok: false, t: "Scrivi prima la tua email." });
    const { error } = await supabase!.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin + window.location.pathname });
    setMsg(error ? { ok: false, t: error.message } : { ok: true, t: "Ti abbiamo inviato un'email per impostare la password." });
  };

  return (
    <div className="grid min-h-screen place-items-center bg-gradient-to-br from-brand-900 to-brand-600 px-4">
      <form onSubmit={entra} className="card w-full max-w-sm p-6">
        <div className="mb-5 flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-700 text-white">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor"><path d="M3 11l9-7 9 7v10H3z" /></svg>
          </span>
          <div>
            <div className="font-semibold">Scout Immobili</div>
            <div className="text-xs text-slate-500">Accesso riservato al team</div>
          </div>
        </div>
        <label className="label" htmlFor="email">Email</label>
        <input id="email" className="input mb-3" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <label className="label" htmlFor="pwd">Password</label>
        <input id="pwd" className="input mb-4" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        <button className="btn-primary w-full" disabled={attesa}>{attesa ? "Accesso…" : "Entra"}</button>
        <button type="button" onClick={recupera} className="mt-3 w-full text-center text-xs text-brand-600 hover:underline">
          Password dimenticata o primo accesso?
        </button>
        {msg && <p className={`mt-3 text-sm ${msg.ok ? "text-emerald-700" : "text-rose-600"}`}>{msg.t}</p>}
      </form>
    </div>
  );
}
