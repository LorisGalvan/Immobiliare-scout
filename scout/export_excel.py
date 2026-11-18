"""Export Excel: un foglio per microzona nel formato dei file manuali + Occasioni + Frazionabili."""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .geo.polygons import casa_search_url, idealista_search_url, immobiliare_search_url

GIALLO = PatternFill("solid", fgColor="FFFF00")      # 0 / +10
VERDE_CHIARO = PatternFill("solid", fgColor="D6E3BC")  # 0 / -10
VERDE = PatternFill("solid", fgColor="00B050")       # -10 / -20
AZZURRO = PatternFill("solid", fgColor="00B0F0")     # da -21
GRIGIO = PatternFill("solid", fgColor="D9D9D9")
INTEST = PatternFill("solid", fgColor="1F4E78")
BOLD = Font(bold=True)
BIANCO = Font(bold=True, color="FFFFFF")
LINK = Font(color="0563C1", underline="single")
SOTTILE = Border(bottom=Side(style="thin", color="BFBFBF"))

COLONNE = ["VIA", "MQ", "PREZZO", "PREZZO MQ", "%SCOSTAMENTO", "PIANO", "ASCENSORE", "BAGNI",
           "RISTRUTTURATO", "DATA", "AGENZIA/PRIVATO", "LINK", "NOTE",
           "FONTE", "GIORNI ONLINE", "RIBASSO %", "SCOST. GREZZO %", "OMI €/MQ", "ALTRI LINK"]
LARGHEZZE = [30, 9, 12, 11, 13, 7, 10, 7, 16, 11, 24, 12, 45, 12, 9, 9, 10, 10, 50]

STATO_TXT = {"nuovo": "nuovo", "ottimo": "si", "buono": "abitabile", "da_ristrutturare": "no (da ristr.)"}


def fill_scostamento(v):
    if v is None or pd.isna(v):
        return None
    if v > 0:
        return GIALLO
    if v > -10:
        return VERDE_CHIARO
    if v > -20:
        return VERDE
    return AZZURRO


def nome_foglio(nome: str, usati: set) -> str:
    s = re.sub(r"[\[\]\:\*\?\/\\]", "-", nome).strip()[:31]
    base, k = s, 2
    while s.lower() in usati:
        suf = f" ({k})"
        s = base[:31 - len(suf)] + suf
        k += 1
    usati.add(s.lower())
    return s


def _si_no(v):
    if v is True:
        return "si"
    if v is False:
        return "no"
    return "nd"


def _val(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


def _note(r) -> str:
    bits = []
    if isinstance(r.get("flags"), list) and r["flags"]:
        bits.append("; ".join(r["flags"]))
    if r.get("base_confronto") and not str(r["base_confronto"]).startswith("fascia"):
        bits.append(f"confronto: {r['base_confronto']}")
    if r.get("coeff") and abs(r["coeff"] - 1) > 0.001:
        bits.append(f"coeff. correzione {r['coeff']:.2f}")
    if r.get("attivo") == 0:
        bits.append(f"RIMOSSO il {r.get('removed_at')}")
    return " | ".join(bits)


def _riga(ws, row: int, r: dict, mq_label: bool = False):
    vals = [
        _val(r.get("indirizzo")) or _val(r.get("titolo")), r["mq"], r["prezzo"], r["prezzo_mq"],
        None if pd.isna(r.get("scostamento_pct")) else r["scostamento_pct"] / 100,
        _val(r.get("piano")) or "nd", _si_no(r.get("ascensore")), _val(r.get("bagni")),
        STATO_TXT.get(r.get("stato"), _val(r.get("stato_raw")) or "nd"),
        _val(r.get("data_pubblicazione")) or str(r.get("first_seen") or "")[:10],
        ("Privato" if r.get("privato") else _val(r.get("agenzia")) or "nd"),
        "apri", _note(r), r.get("source"), _val(r.get("giorni_online")),
        (r["ribasso_pct"] / 100) if r.get("ribasso_pct") else None,
        None if pd.isna(r.get("scostamento_grezzo_pct", float("nan"))) else r["scostamento_grezzo_pct"] / 100,
        _val(((r.get("omi_min") or 0) + (r.get("omi_max") or 0)) / 2 if _val(r.get("omi_min")) else None),
        "\n".join(r.get("doppioni") or []) if isinstance(r.get("doppioni"), list) else "",
    ]
    for c, v in enumerate(vals, 1):
        cell = ws.cell(row, c, v)
        cell.border = SOTTILE
    ws.cell(row, 3).number_format = '#,##0 "€"'
    ws.cell(row, 4).number_format = '#,##0 "€"'
    ws.cell(row, 5).number_format = "0.0%"
    ws.cell(row, 16).number_format = "0.0%"
    ws.cell(row, 17).number_format = "0.0%"
    ws.cell(row, 18).number_format = '#,##0'
    f = fill_scostamento(r.get("scostamento_pct"))
    if f:
        ws.cell(row, 5).fill = f
    if r.get("url"):
        ws.cell(row, 12).hyperlink = r["url"]
        ws.cell(row, 12).font = LINK
    if r.get("attivo") == 0:
        for c in range(1, 12):
            ws.cell(row, c).font = Font(color="808080", strike=True)


def _intestazione(ws, row: int, etichetta_mq: str):
    for c, h in enumerate(COLONNE, 1):
        cell = ws.cell(row, c, f"MQ {etichetta_mq}" if h == "MQ" else h)
        cell.font = BIANCO
        cell.fill = INTEST
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _legenda(ws, col: int = 21, row: int = 5):
    ws.cell(row, col, "Legenda scostamento").font = BOLD
    for i, (txt, fill) in enumerate([("> 0 (sopra mediana)", GIALLO), ("0 / -10", VERDE_CHIARO),
                                     ("-10 / -20", VERDE), ("da -20", AZZURRO)], 1):
        c = ws.cell(row + i, col, txt)
        c.fill = fill


def _larghezze(ws):
    for i, w in enumerate(LARGHEZZE, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def foglio_zona(wb, nome_sh: str, zona, df_z: pd.DataFrame, med_z: pd.DataFrame, fasce, slug: str):
    ws = wb.create_sheet(nome_sh)
    _larghezze(ws)
    if zona is not None:
        pts = zona.latlon
        links = [("Immobiliare", immobiliare_search_url(pts, slug)), ("Idealista", idealista_search_url(pts)),
                 ("Casa", casa_search_url(pts))]
        for i, (lab, url) in enumerate(links, 1):
            ws.cell(i, 1, lab).font = BOLD
            c = ws.cell(i, 2, url)
            c.hyperlink = url
            c.font = LINK
    row = 5
    etichette = [f[2] for f in fasce] + [x for x in df_z["fascia"].unique() if x not in [f[2] for f in fasce]]
    for lab in etichette:
        sub = df_z[df_z["fascia"] == lab].sort_values("scostamento_pct", na_position="last")
        _intestazione(ws, row, lab)
        row += 1
        for _, r in sub.iterrows():
            _riga(ws, row, r.to_dict())
            row += 1
        m = med_z[med_z["fascia"] == lab]
        attivi = sub[sub["attivo"] == 1]
        ws.cell(row, 2, "Mediana").font = BOLD
        if not m.empty:
            ws.cell(row, 4, float(m["mediana_mq"].iloc[0])).number_format = '#,##0 "€"'
            ws.cell(row, 5, f"n={int(m['n'].iloc[0])}")
        ws.cell(row, 3, float(sub["prezzo"].median()) if len(sub) else None)
        ws.cell(row, 3).number_format = '#,##0 "€"'
        for c in range(1, 14):
            ws.cell(row, c).fill = GRIGIO
        row += 1
        ws.cell(row, 2, "Media")
        if len(sub):
            ws.cell(row, 3, float(sub["prezzo"].mean())).number_format = '#,##0 "€"'
            ws.cell(row, 4, float(sub["prezzo_mq"].mean())).number_format = '#,##0 "€"'
            ws.cell(row, 5, f"attivi {len(attivi)}")
        row += 3
    _legenda(ws)
    ws.freeze_panes = "B5"


def _tabella(ws, df: pd.DataFrame, cols: list[tuple[str, str, str | None]], start_row: int = 1):
    """cols: (intestazione, colonna df, formato)"""
    for c, (h, _, _) in enumerate(cols, 1):
        cell = ws.cell(start_row, c, h)
        cell.font = BIANCO
        cell.fill = INTEST
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for i, (_, r) in enumerate(df.iterrows(), start_row + 1):
        for c, (h, col, fmt) in enumerate(cols, 1):
            v = r.get(col)
            if isinstance(v, list):
                v = "; ".join(map(str, v))
            v = _val(v)
            if fmt == "pct" and v is not None:
                v = v / 100
            cell = ws.cell(i, c, v)
            if fmt == "eur":
                cell.number_format = '#,##0 "€"'
            elif fmt == "pct":
                cell.number_format = "0.0%"
            if col == "url" and v:
                cell.hyperlink = v
                cell.value = "apri"
                cell.font = LINK
            if col == "scostamento_pct":
                f = fill_scostamento(r.get("scostamento_pct"))
                if f:
                    cell.fill = f
    ws.freeze_panes = ws.cell(start_row + 1, 1)
    ws.auto_filter.ref = f"A{start_row}:{get_column_letter(len(cols))}{start_row + max(len(df), 1)}"


COL_OCCASIONI = [
    ("Microzona", "microzona", None), ("Fascia", "fascia", None), ("Via", "indirizzo", None),
    ("Titolo", "titolo", None), ("MQ", "mq", None), ("Prezzo", "prezzo", "eur"),
    ("€/mq", "prezzo_mq", "eur"), ("Mediana rif. €/mq", "riferimento_mq", "eur"),
    ("% scostamento", "scostamento_pct", "pct"), ("Base confronto", "base_confronto", None),
    ("Piano", "piano", None), ("Ascensore", "ascensore", None), ("Bagni", "bagni", None),
    ("Stato", "stato", None), ("Agenzia", "agenzia", None), ("Privato", "privato", None),
    ("Giorni online", "giorni_online", None), ("Ribasso %", "ribasso_pct", "pct"),
    ("Fonte", "source", None), ("Link", "url", None), ("Segnalazioni", "flags", None),
    ("Altri link", "doppioni", None),
]

COL_FRAZ = [
    ("Microzona", "microzona", None), ("Via", "indirizzo", None), ("Titolo", "titolo", None),
    ("MQ", "mq", None), ("Prezzo", "prezzo", "eur"), ("€/mq", "prezzo_mq", "eur"),
    ("% scost. zona", "scostamento_pct", "pct"), ("N unità", "n_unita", None),
    ("MQ per unità", "mq_unita", None), ("Mediana piccole €/mq", "mediana_piccole_mq", "eur"),
    ("n campione", "n_campione_piccole", None), ("Valore post", "valore_post", "eur"),
    ("Lavori+tecniche", "costo_lavori", "eur"), ("Impianti+oneri", "costo_impianti_oneri", "eur"),
    ("Notaio/provv.", "costi_transazione", "eur"), ("Costi totali", "costi_totali", "eur"),
    ("Margine €", "margine", "eur"), ("Margine %", "margine_pct", "pct"),
    ("Indizi testo", "indizi", None), ("Punteggio indizi", "punteggio_indizi", None),
    ("Piano", "piano", None), ("Bagni", "bagni", None), ("Fonte", "source", None), ("Link", "url", None),
    ("Stesso lotto anche su", "doppioni", None),
]


COL_ASTE = [
    ("Tipo", "tipo_vendita", None), ("Microzona", "microzona", None), ("Fascia", "fascia", None),
    ("Via", "indirizzo", None), ("Titolo", "titolo", None), ("MQ", "mq", None), ("Prezzo annuncio", "prezzo", "eur"),
    ("€/mq", "prezzo_mq", "eur"), ("Mediana mercato €/mq", "riferimento_mq", "eur"), ("Base confronto", "base_confronto", None),
    ("% vs mercato", "scostamento_pct", "pct"), ("Valore di mercato", "valore_mercato", "eur"),
    ("Prezzo base", "prezzo_base", "eur"), ("Offerta minima", "offerta_minima", "eur"),
    ("% offerta minima vs mercato", "scostamento_minima_pct", "pct"), ("Data asta", "data_asta", None),
    ("Diritto", "diritto", None), ("Occupazione", "occupazione", None),
    ("Indizi nel testo", "indizi_vendita", None), ("Agenzia", "agenzia", None), ("Fonte", "source", None), ("Link", "url", None),
    ("Stesso lotto anche su", "doppioni", None),
]


def esporta(path, df: pd.DataFrame, med: pd.DataFrame, fraz: pd.DataFrame, zone_set, cfg: dict,
            aste: pd.DataFrame | None = None) -> str:
    fasce = cfg.get("analisi", {}).get("fasce_mq")
    slug = cfg["territorio"].get("slug_immobiliare", "verona")
    wb = Workbook()
    ws = wb.active
    ws.title = "Riepilogo"
    usati = {"riepilogo", "occasioni", "aste", "frazionabili", "ribassi", "fuori zona"}

    # ---- Riepilogo
    ws.cell(1, 1, f"Scout immobili - {cfg['territorio']['nome']} - {dt.date.today():%d/%m/%Y}").font = Font(bold=True, size=14)
    attivi = df[df["attivo"] == 1] if not df.empty else df
    n_aste = 0 if aste is None or aste.empty else len(aste)
    ws.cell(2, 1, f"Annunci attivi analizzati: {len(attivi)} | occasioni: {int(df['occasione'].sum()) if not df.empty else 0}"
                  f" | soglia {cfg['analisi'].get('soglia_occasione_pct')}% | aste escluse dalla valutazione: {n_aste}")
    hdr = ["Microzona", "Annunci"] + [f"{f[2]} mediana €/mq" for f in fasce] + [f"{f[2]} n" for f in fasce] + ["Mediana zona €/mq"]
    for c, h in enumerate(hdr, 1):
        cell = ws.cell(4, c, h)
        cell.font = BIANCO
        cell.fill = INTEST
        cell.alignment = Alignment(wrap_text=True)
    row = 5
    for nome in zone_set.names():
        m = med[med["microzona"] == nome] if not med.empty else med
        ws.cell(row, 1, nome)
        ws.cell(row, 2, int(m["n"].sum()) if not m.empty else 0)
        for i, f in enumerate(fasce):
            mm = m[m["fascia"] == f[2]] if not m.empty else m
            if not mm.empty:
                ws.cell(row, 3 + i, float(mm["mediana_mq"].iloc[0])).number_format = '#,##0'
                ws.cell(row, 3 + len(fasce) + i, int(mm["n"].iloc[0]))
        if not m.empty:
            ws.cell(row, 3 + 2 * len(fasce), float(m["mediana_zona"].iloc[0])).number_format = '#,##0'
        row += 1
    ws.column_dimensions["A"].width = 32
    ws.freeze_panes = "B5"

    # ---- Occasioni
    wo = wb.create_sheet("Occasioni")
    occ = df[df["occasione"]].sort_values("scostamento_pct") if not df.empty else df
    _tabella(wo, occ, COL_OCCASIONI)
    for i, w in enumerate([22, 8, 26, 40, 6, 11, 9, 11, 10, 18, 6, 8, 6, 14, 20, 7, 8, 8, 11, 6, 40, 40], 1):
        wo.column_dimensions[get_column_letter(i)].width = w

    # ---- Aste (fuori dalla valutazione, confrontate con il mercato libero della zona)
    wa = wb.create_sheet("Aste")
    if aste is not None and not aste.empty:
        wa.cell(1, 1, "Aste e possibili aste riconosciute dal testo degli annunci: NON entrano nelle mediane. "
                      "'possibile_asta' = un solo indizio, controlla l'annuncio.").font = Font(italic=True)
        unisci = lambda v: ", ".join(v) if isinstance(v, list) else v  # noqa: E731
        _tabella(wa, aste.assign(indizi_vendita=aste["indizi_vendita"].apply(unisci),
                                 doppioni=aste.get("doppioni", pd.Series(dtype=object)).apply(
                                     lambda v: " | ".join(v) if isinstance(v, list) else v)), COL_ASTE, start_row=3)
        for i, w in enumerate([14, 22, 8, 26, 34, 6, 12, 9, 11, 16, 9, 12, 12, 12, 11, 11, 16, 16, 40, 20, 11, 8, 40], 1):
            wa.column_dimensions[get_column_letter(i)].width = w
    else:
        wa.cell(1, 1, "Nessuna asta riconosciuta tra gli annunci attivi.")

    # ---- Frazionabili
    wf = wb.create_sheet("Frazionabili")
    if fraz is not None and not fraz.empty:
        _tabella(wf, fraz, COL_FRAZ)
    else:
        wf.cell(1, 1, "Nessun candidato sopra il margine minimo configurato.")
    for i in range(1, len(COL_FRAZ) + 1):
        wf.column_dimensions[get_column_letter(i)].width = 13
    wf.column_dimensions["C"].width = 40
    wf.column_dimensions["S"].width = 40

    # ---- Ribassi
    wr = wb.create_sheet("Ribassi")
    rib = df[(df["ribasso_pct"] < 0) & (df["attivo"] == 1)].sort_values("ribasso_pct") if not df.empty else df
    _tabella(wr, rib, [("Microzona", "microzona", None), ("Via", "indirizzo", None), ("MQ", "mq", None),
                       ("Prezzo iniziale", "prezzo_iniziale", "eur"), ("Prezzo attuale", "prezzo", "eur"),
                       ("Ribasso %", "ribasso_pct", "pct"), ("% scostamento", "scostamento_pct", "pct"),
                       ("Giorni online", "giorni_online", None), ("Fonte", "source", None), ("Link", "url", None)])

    # ---- Fogli microzona
    for z in zone_set.zone:
        df_z = df[df["microzona"] == z.nome] if not df.empty else df
        med_z = med[med["microzona"] == z.nome] if not med.empty else med
        if df_z.empty:
            df_z = pd.DataFrame(columns=list(dict.fromkeys(list(df.columns) + ["fascia", "attivo", "prezzo"])))
        foglio_zona(wb, nome_foglio(z.nome, usati), z, df_z, med_z, fasce, slug)

    # ---- Fuori zona
    fz = df[df["microzona"].isna()] if not df.empty else df
    if not fz.empty:
        wz = wb.create_sheet("Fuori zona")
        _tabella(wz, fz, [("Via", "indirizzo", None), ("Titolo", "titolo", None), ("MQ", "mq", None),
                          ("Prezzo", "prezzo", "eur"), ("€/mq", "prezzo_mq", "eur"), ("Lat", "lat", None),
                          ("Lon", "lon", None), ("Fonte", "source", None), ("Link", "url", None),
                          ("Segnalazioni", "flags", None)])
    wb.save(path)
    return str(path)
