import shutil
from pathlib import Path

from scout.importa import importa_html

FIX = Path(__file__).parent / "fixtures"


def test_archivia(tmp_path):
    shutil.copy(FIX / "immobiliare_lista.html", tmp_path / "Vendita case Verona.html")
    (tmp_path / "Vendita case Verona_files").mkdir()          # "pagina web completa"
    (tmp_path / "Vendita case Verona_files" / "x.htm").write_text("<html>risorsa</html>")
    (tmp_path / "altro.html").write_text("<html>niente</html>")
    res = importa_html(tmp_path, archivia=True)
    assert len(res) == 3
    assert not (tmp_path / "Vendita case Verona.html").exists()
    arch = list((tmp_path / "importate").glob("*/*.html"))
    assert len(arch) == 1 and (arch[0].parent / (arch[0].stem + "_files")).is_dir()
    assert (tmp_path / "non_riconosciute" / "altro.html").exists()
    assert importa_html(tmp_path, archivia=True) == []        # già archiviati: non reimporta
