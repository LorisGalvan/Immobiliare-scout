"""Modello dati di un annuncio."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Listing:
    source: str                     # immobiliare | subito | idealista | facebook | excel
    source_id: str
    url: str = ""
    titolo: str = ""
    descrizione: str = ""
    prezzo: Optional[float] = None
    mq: Optional[float] = None
    piano: Optional[str] = None     # testo normalizzato: "T", "R", "1", "2", ..., "A" (attico)
    ascensore: Optional[bool] = None
    bagni: Optional[int] = None
    locali: Optional[int] = None
    stato: Optional[str] = None     # nuovo | ottimo | buono | da_ristrutturare
    stato_raw: Optional[str] = None
    agenzia: Optional[str] = None
    privato: Optional[bool] = None
    data_pubblicazione: Optional[str] = None   # ISO date
    indirizzo: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    coord_precise: bool = True      # False se da geocoding approssimativo
    tipologia: Optional[str] = None
    comune: Optional[str] = None    # comune della ricerca (vuoto nei dati vecchi = comune principale)
    prezzo_ribassato_da: Optional[float] = None
    # campi calcolati
    microzona: Optional[str] = None
    tipo_vendita: Optional[str] = None   # compravendita | asta | possibile_asta (da tipo_vendita.py)
    indizi_vendita: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    doppioni: list = field(default_factory=list)   # altri link dello stesso immobile

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def prezzo_mq(self) -> Optional[float]:
        if self.prezzo and self.mq:
            return self.prezzo / self.mq
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uid"] = self.uid
        d["prezzo_mq"] = self.prezzo_mq
        return d
