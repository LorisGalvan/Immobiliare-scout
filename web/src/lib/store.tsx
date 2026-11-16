import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { DEMO, supabase, TIPO_LINK } from "./supabase";
import { caricaDataset, territori as listaTerritori, valutazioni as caricaValutazioni } from "./data";
import type { Dataset, Valutazione } from "./types";

// ------------------------------------------------------------------ Auth
interface Utente { id: string; email: string }
interface AuthCtx { utente: Utente | null; pronto: boolean; esci: () => Promise<void> }
const AuthContext = createContext<AuthCtx>({ utente: null, pronto: false, esci: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [sessione, setSessione] = useState<Session | null>(null);
  const [pronto, setPronto] = useState(DEMO);
  useEffect(() => {
    if (DEMO) return;
    supabase!.auth.getSession().then(({ data }) => { setSessione(data.session); setPronto(true); });
    const { data } = supabase!.auth.onAuthStateChange((evento, s) => {
      setSessione(s);
      // invito o recupero password: porta l'utente a impostare la password
      if (s && (evento === "PASSWORD_RECOVERY" || (evento === "SIGNED_IN" && TIPO_LINK && ["invite", "recovery", "signup", "magiclink"].includes(TIPO_LINK)))) {
        window.location.replace(window.location.pathname + "#/password");
      }
    });
    return () => data.subscription.unsubscribe();
  }, []);
  const utente = DEMO
    ? { id: "demo", email: "demo@esempio.it" }
    : sessione ? { id: sessione.user.id, email: sessione.user.email ?? "" } : null;
  const esci = async () => { if (!DEMO) await supabase!.auth.signOut(); };
  return <AuthContext.Provider value={{ utente, pronto, esci }}>{children}</AuthContext.Provider>;
}
export const useAuth = () => useContext(AuthContext);

// ------------------------------------------------------------------ Dati
interface DataCtx {
  territori: string[];
  territorio: string | null;
  setTerritorio: (t: string) => void;
  dataset: Dataset | null;
  errore: string | null;
  caricamento: boolean;
  soglia: number;
  setSoglia: (s: number) => void;
  valutazioni: Valutazione[];
  ricaricaValutazioni: () => void;
}
const DataContext = createContext<DataCtx>(null as unknown as DataCtx);

const leggi = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
const scrivi = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* ignora */ } };

export function DataProvider({ children }: { children: ReactNode }) {
  const [territori, setTerritori] = useState<string[]>([]);
  const [territorio, setTerritorioS] = useState<string | null>(leggi("scout-territorio"));
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [caricamento, setCaricamento] = useState(true);
  const [soglia, setSogliaS] = useState<number>(Number(leggi("scout-soglia")) || NaN);
  const [valutazioni, setValutazioni] = useState<Valutazione[]>([]);

  useEffect(() => {
    listaTerritori()
      .then((t) => {
        setTerritori(t);
        if (!territorio || !t.includes(territorio)) setTerritorioS(t[0] ?? null);
        if (!t.length) setCaricamento(false);
      })
      .catch((e) => { setErrore(String(e.message ?? e)); setCaricamento(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!territorio) return;
    setCaricamento(true);
    caricaDataset(territorio)
      .then((d) => { setDataset(d); setErrore(null); })
      .catch((e) => setErrore(String(e.message ?? e)))
      .finally(() => setCaricamento(false));
  }, [territorio]);

  const ricaricaValutazioni = useCallback(() => {
    caricaValutazioni().then(setValutazioni).catch(() => {});
  }, []);
  useEffect(ricaricaValutazioni, [ricaricaValutazioni]);

  const value = useMemo<DataCtx>(() => ({
    territori, territorio, dataset, errore, caricamento, valutazioni, ricaricaValutazioni,
    setTerritorio: (t) => { scrivi("scout-territorio", t); setTerritorioS(t); },
    soglia: isNaN(soglia) ? (dataset?.soglia ?? -15) : soglia,
    setSoglia: (s) => { scrivi("scout-soglia", String(s)); setSogliaS(s); },
  }), [territori, territorio, dataset, errore, caricamento, soglia, valutazioni, ricaricaValutazioni]);
  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}
export const useData = () => useContext(DataContext);
