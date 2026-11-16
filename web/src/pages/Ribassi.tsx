import { useMemo } from "react";
import { useData } from "../lib/store";
import ListaAnnunci from "../components/ListaAnnunci";
import { Titolo } from "../components/ui";

export default function Ribassi() {
  const { dataset } = useData();
  const lista = useMemo(() => dataset?.annunci.filter((a) => a.attivo && (a.ribasso_pct ?? 0) < 0)
    .sort((a, b) => a.ribasso_pct! - b.ribasso_pct!) ?? [], [dataset]);
  return (
    <>
      <Titolo sotto="Annunci attivi con prezzo ridotto rispetto alla prima rilevazione: venditore che tratta">
        Ribassi <span className="text-slate-400">({lista.length})</span>
      </Titolo>
      <ListaAnnunci annunci={lista} vuoto="Nessun ribasso registrato." />
    </>
  );
}
