import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { supabase } from "../lib/supabase";
import { Titolo } from "../components/ui";

export default function ImpostaPassword() {
  const [pwd, setPwd] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const nav = useNavigate();
  const salva = async (e: FormEvent) => {
    e.preventDefault();
    const { error } = await supabase!.auth.updateUser({ password: pwd });
    if (error) setMsg(error.message); else nav("/");
  };
  return (
    <form onSubmit={salva} className="card mx-auto max-w-sm p-6">
      <Titolo sotto="Benvenuto! Scegli la password che userai per accedere.">Imposta la password</Titolo>
      <input className="input mb-3" type="password" minLength={8} required value={pwd} onChange={(e) => setPwd(e.target.value)} placeholder="Almeno 8 caratteri" />
      <button className="btn-primary w-full">Salva</button>
      {msg && <p className="mt-3 text-sm text-rose-600">{msg}</p>}
    </form>
  );
}
