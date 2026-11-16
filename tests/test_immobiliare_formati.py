import json
from pathlib import Path

from scout.scrapers import immobiliare

FIX = Path(__file__).parent / "fixtures"


def _risultati():
    html = (FIX / "immobiliare_lista.html").read_text()
    nd = json.loads(html.split('type="application/json">')[1].split("</script>")[0])
    return nd["props"]["pageProps"]["dehydratedState"]["queries"][0]["state"]["data"]


def test_flusso_rsc():
    data = _risultati()
    payload = '1:["$","div",null,' + json.dumps({"data": data}) + "]\n"
    meta = len(payload) // 2   # il payload arriva spezzato in più push
    chunks = [payload[:meta], payload[meta:]]
    html = "<html><body>immobiliare.it" + "".join(
        f"<script>self.__next_f.push([1,{json.dumps(c)}])</script>" for c in chunks) + "</body></html>"
    ls, maxp = immobiliare.parse_search_page(html)
    assert len(ls) == 3 and maxp == 1
    assert {l.source_id for l in ls} == {"101", "102", "103"} and ls[0].lat


def test_solo_html_visibile():
    html = """<html><body>immobiliare.it<ul>
    <li class="nd-list__item"><div><a href="https://www.immobiliare.it/annunci/1234567/" title="Trilocale via Mameli 12, Borgo Trento, Verona">Trilocale</a></div>
      <div>€ 245.000</div><ul><li>3 locali</li><li>85 m²</li><li>2 bagni</li><li>Piano 2</li></ul></li>
    <li class="nd-list__item"><a href="/annunci/7654321/">Bilocale via Roma, Centro</a><span>€ 180.000</span><span>52 m²</span></li>
    </ul></body></html>"""
    ls, _ = immobiliare.parse_search_page(html)
    a = {l.source_id: l for l in ls}
    assert a["1234567"].prezzo == 245000 and a["1234567"].mq == 85 and a["1234567"].bagni == 2
    assert a["1234567"].indirizzo == "via Mameli 12"
    assert a["7654321"].indirizzo == "via Roma"
    assert a["7654321"].url == "https://www.immobiliare.it/annunci/7654321/"
