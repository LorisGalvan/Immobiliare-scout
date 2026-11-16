"""Mappe HTML con folium: microzone colorate per €/mq e annunci occasione."""
from __future__ import annotations

import html
import json

import branca.colormap as cm
import folium
import pandas as pd
from folium.plugins import Draw
from shapely.geometry import mapping


def _centro(zone_set):
    if len(zone_set):
        x, y = zone_set.union_bounds_center()
        return [y, x]
    return [45.4384, 10.9916]


def mappa_analisi(path, zone_set, df: pd.DataFrame, med: pd.DataFrame, fraz: pd.DataFrame | None = None,
                  titolo: str = "Scout immobili") -> str:
    m = folium.Map(location=_centro(zone_set), zoom_start=13, tiles="OpenStreetMap")
    med_zona = {}
    if not med.empty:
        med_zona = med.groupby("microzona")["mediana_zona"].first().to_dict()
    vals = [v for v in med_zona.values() if pd.notna(v)]
    cmap = cm.LinearColormap(["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"],
                             vmin=min(vals) if vals else 1000, vmax=max(vals) if vals else 5000,
                             caption="Mediana €/mq microzona")

    fg_z = folium.FeatureGroup(name="Microzone")
    for z in zone_set.zone:
        v = med_zona.get(z.nome)
        righe = ""
        if not med.empty:
            for _, r in med[med["microzona"] == z.nome].iterrows():
                righe += f"<tr><td>{r['fascia']}</td><td>{r['mediana_mq']:,.0f} €</td><td>n={int(r['n'])}</td></tr>"
        popup = (f"<b>{html.escape(z.nome)}</b><br>Mediana zona: "
                 f"{'n.d.' if v is None or pd.isna(v) else f'{v:,.0f} €/mq'}"
                 f"<table>{righe}</table>")
        folium.GeoJson(
            mapping(z.geom),
            style_function=lambda _f, v=v: {"fillColor": cmap(v) if v is not None and pd.notna(v) else "#cccccc",
                                            "color": "#333", "weight": 1.2, "fillOpacity": 0.45},
            tooltip=z.nome, popup=folium.Popup(popup, max_width=320),
        ).add_to(fg_z)
    fg_z.add_to(m)
    cmap.add_to(m)

    fg_all = folium.FeatureGroup(name="Tutti gli annunci", show=False)
    fg_occ = folium.FeatureGroup(name="Occasioni")
    fg_fr = folium.FeatureGroup(name="Frazionabili")

    def popup_annuncio(r):
        sc = r.get("scostamento_pct")
        return folium.Popup(
            f"<b>{html.escape(str(r.get('indirizzo') or r.get('titolo') or ''))}</b><br>"
            f"{r['mq']:.0f} mq - {r['prezzo']:,.0f} € ({r['prezzo_mq']:,.0f} €/mq)<br>"
            f"Scostamento: {'n.d.' if pd.isna(sc) else f'{sc:+.1f}%'} ({html.escape(str(r.get('base_confronto')))})<br>"
            f"{html.escape(str(r.get('microzona')))} - {r.get('source')}<br>"
            f"<a href='{html.escape(str(r.get('url')))}' target='_blank'>apri annuncio</a>", max_width=300)

    if not df.empty:
        for _, r in df[(df["attivo"] == 1) & df["lat"].notna()].iterrows():
            if r.get("occasione"):
                folium.Marker([r["lat"], r["lon"]], popup=popup_annuncio(r),
                              icon=folium.Icon(color="red", icon="star")).add_to(fg_occ)
            folium.CircleMarker([r["lat"], r["lon"]], radius=3, color="#555", fill=True,
                                popup=popup_annuncio(r)).add_to(fg_all)
    if fraz is not None and not fraz.empty:
        for _, r in fraz[fraz["lat"].notna()].iterrows():
            folium.Marker([r["lat"], r["lon"]],
                          popup=folium.Popup(f"<b>Frazionabile</b>: {r['n_unita']} unità, "
                                             f"margine {r['margine_pct']:.0f}%<br>{html.escape(str(r.get('indizi')))}"
                                             f"<br><a href='{html.escape(str(r['url']))}' target='_blank'>apri</a>",
                                             max_width=300),
                          icon=folium.Icon(color="purple", icon="th-large")).add_to(fg_fr)
    for fg in (fg_all, fg_occ, fg_fr):
        fg.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.get_root().html.add_child(folium.Element(
        f"<div style='position:fixed;top:10px;left:50px;z-index:999;background:white;padding:6px 10px;"
        f"border-radius:4px;font:14px sans-serif;box-shadow:0 1px 4px #888'><b>{html.escape(titolo)}</b></div>"))
    m.save(str(path))
    return str(path)


def editor_microzone(path, zone_set) -> str:
    """Mappa con strumenti di disegno: modifica/aggiungi/elimina poligoni ed esporta GeoJSON.

    Dopo l'export ("Export" in alto a destra) salva il file e importalo con
    ``scout zone-importa-geojson file.geojson``.
    """
    m = folium.Map(location=_centro(zone_set), zoom_start=13, tiles="OpenStreetMap")
    fg = folium.FeatureGroup(name="Microzone")
    for z in zone_set.zone:
        gj = folium.GeoJson({"type": "Feature", "properties": {**{k: v for k, v in z.props.items()
                                                                  if isinstance(v, (str, int, float))},
                                                               "nome": z.nome},
                             "geometry": mapping(z.geom)},
                            tooltip=z.nome,
                            style_function=lambda _f: {"color": "#d33", "weight": 2, "fillOpacity": 0.15})
        # ogni layer GeoJSON deve finire direttamente nel gruppo modificabile
        for child in [gj]:
            child.add_to(fg)
        folium.Marker(list(reversed(z.geom.representative_point().coords[0])),
                      icon=folium.DivIcon(html=f"<div style='font:11px sans-serif;color:#900;white-space:nowrap'>"
                                               f"{html.escape(z.nome)}</div>")).add_to(m)
    fg.add_to(m)
    Draw(export=True, filename="microzone_modificate.geojson", feature_group=fg,
         draw_options={"polyline": False, "circle": False, "circlemarker": False, "marker": False,
                       "rectangle": True, "polygon": True},
         edit_options={"edit": True, "remove": True}).add_to(m)
    m.get_root().html.add_child(folium.Element(
        "<div style='position:fixed;bottom:20px;left:10px;z-index:999;background:white;padding:8px;"
        "font:13px sans-serif;max-width:360px;box-shadow:0 1px 4px #888'>"
        "<b>Editor microzone</b><br>Matita = modifica vertici, cestino = elimina, pentagono = nuova zona.<br>"
        "I nuovi poligoni non hanno nome: lo assegni nel file o con <code>scout zone-rinomina</code>.<br>"
        "Al termine premi <b>Export</b> e importa il file con <code>scout zone-importa-geojson</code>.</div>"))
    m.save(str(path))
    return str(path)


__all__ = ["mappa_analisi", "editor_microzone", "json"]
