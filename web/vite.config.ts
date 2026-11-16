import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = { ...process.env, ...loadEnv(mode, process.cwd(), "VITE_") };
  const conSupabase = Boolean(env.VITE_SUPABASE_URL && env.VITE_SUPABASE_ANON_KEY);
  return {
    plugins: [react()],
    base: "./",
    // public/ contiene solo demo.json (con le tue microzone): non va pubblicato quando il sito usa Supabase
    publicDir: conSupabase ? false : "public",
  };
});
