import { createClient, SupabaseClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const DEMO = !url || !key;

// Tipo di link email (invito / recupero password) letto PRIMA che supabase-js consumi il token nell'URL.
const frammento = new URLSearchParams(window.location.hash.replace(/^#\/?/, ""));
export const TIPO_LINK = frammento.get("access_token") ? frammento.get("type") : null;

export const supabase: SupabaseClient | null = DEMO ? null : createClient(url!, key!);
