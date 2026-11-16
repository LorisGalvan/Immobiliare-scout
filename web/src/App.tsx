import { HashRouter, Route, Routes } from "react-router-dom";
import { DEMO } from "./lib/supabase";
import { AuthProvider, DataProvider, useAuth, useData } from "./lib/store";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Panoramica from "./pages/Panoramica";
import Occasioni from "./pages/Occasioni";
import MappaPage from "./pages/MappaPage";
import Microzone from "./pages/Microzone";
import Zona from "./pages/Zona";
import Frazionabili from "./pages/Frazionabili";
import Ribassi from "./pages/Ribassi";
import Annuncio from "./pages/Annuncio";
import ImpostaPassword from "./pages/ImpostaPassword";
import EditorZone from "./pages/EditorZone";
import { Vuoto } from "./components/ui";

function Contenuto() {
  const { caricamento, errore, dataset, territori } = useData();
  if (errore) return <Vuoto><b className="text-rose-600">Errore nel caricamento dei dati:</b> {errore}</Vuoto>;
  if (caricamento && !dataset) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => <div key={i} className="h-20 animate-pulse rounded-xl bg-slate-200" />)}
      </div>
    );
  }
  if (!territori.length) return <Vuoto>Nessun dato ancora pubblicato. Esegui il bot con Supabase attivo (vedi README).</Vuoto>;
  return (
    <Routes>
      <Route path="/" element={<Panoramica />} />
      <Route path="/occasioni" element={<Occasioni />} />
      <Route path="/mappa" element={<MappaPage />} />
      <Route path="/microzone" element={<Microzone />} />
      <Route path="/microzone/:nome" element={<Zona />} />
      <Route path="/editor-zone" element={<EditorZone />} />
      <Route path="/frazionabili" element={<Frazionabili />} />
      <Route path="/ribassi" element={<Ribassi />} />
      <Route path="/annuncio/:uid" element={<Annuncio />} />
      <Route path="/password" element={<ImpostaPassword />} />
      <Route path="*" element={<Vuoto>Pagina non trovata.</Vuoto>} />
    </Routes>
  );
}

function Protetto() {
  const { utente, pronto } = useAuth();
  if (!pronto) return null;
  if (!utente && !DEMO) return <Login />;
  return (
    <DataProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route path="*" element={<Contenuto />} />
        </Route>
      </Routes>
    </DataProvider>
  );
}

export default function App() {
  return (
    <HashRouter>
      <AuthProvider>
        <Protetto />
      </AuthProvider>
    </HashRouter>
  );
}
