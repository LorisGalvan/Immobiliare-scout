import { NavLink, Outlet } from "react-router-dom";
import { DEMO } from "../lib/supabase";
import { useAuth, useData } from "../lib/store";
import { ICONE, Icona } from "./ui";
import Chat from "./Chat";

const VOCI = [
  { to: "/", label: "Panoramica", icona: ICONE.home, end: true },
  { to: "/occasioni", label: "Occasioni", icona: ICONE.stella },
  { to: "/mappa", label: "Mappa", icona: ICONE.mappa },
  { to: "/microzone", label: "Microzone", icona: ICONE.zone },
  { to: "/frazionabili", label: "Frazionabili", icona: ICONE.forbici },
  { to: "/ribassi", label: "Ribassi", icona: ICONE.freccia },
  { to: "/aste", label: "Aste", icona: ICONE.martello },
];

export default function Layout() {
  const { utente, esci } = useAuth();
  const { territori, territorio, setTerritorio } = useData();
  return (
    <div className="min-h-screen pb-20 md:pb-0">
      {DEMO && (
        <div className="bg-amber-100 px-4 py-1.5 text-center text-xs text-amber-900">
          Modalità <b>DEMO</b>: annunci simulati nelle tue microzone reali. Collega Supabase per i dati veri.
        </div>
      )}
      <header className="sticky top-0 z-[1000] border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
          <NavLink to="/" className="flex items-center gap-2 font-semibold text-brand-700">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-700 text-white">
              <Icona d={ICONE.home} className="h-4 w-4" />
            </span>
            <span className="hidden sm:inline">Scout Immobili</span>
          </NavLink>
          <nav className="hidden flex-1 items-center gap-1 md:flex">
            {VOCI.map((v) => (
              <NavLink key={v.to} to={v.to} end={v.end}
                className={({ isActive }) => `rounded-lg px-3 py-1.5 text-sm font-medium ${isActive ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-100"}`}>
                {v.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {territori.length > 1 ? (
              <select className="input w-auto py-1.5" value={territorio ?? ""} onChange={(e) => setTerritorio(e.target.value)}>
                {territori.map((t) => <option key={t}>{t}</option>)}
              </select>
            ) : (
              <span className="text-sm font-medium text-slate-600">{territorio}</span>
            )}
            <span className="hidden text-xs text-slate-400 lg:inline">{utente?.email}</span>
            {!DEMO && (
              <>
                <NavLink to="/password" className="btn-ghost hidden px-2 text-xs sm:inline-flex" title="Cambia password">Password</NavLink>
                <button className="btn-ghost px-2" onClick={esci} title="Esci"><Icona d={ICONE.esci} /></button>
              </>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-5 sm:py-6">
        <Outlet />
      </main>
      {territorio && <Chat />}
      <nav className="fixed inset-x-0 bottom-0 z-[1000] grid grid-cols-7 border-t border-slate-200 bg-white md:hidden">
        {VOCI.map((v) => (
          <NavLink key={v.to} to={v.to} end={v.end}
            className={({ isActive }) => `flex flex-col items-center gap-0.5 py-2 text-[10px] font-medium ${isActive ? "text-brand-700" : "text-slate-500"}`}>
            <Icona d={v.icona} className="h-5 w-5" />
            {v.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
