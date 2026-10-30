"""Comprovantes de pagamento do Santander (PDF) e casamento com o "PAGAMENTO DE TITULO" do extrato.

O extrato traz só "PAGAMENTO DE TITULO 4204.4907055541", sem o fornecedor. Os PDFs salvos no
Internet Banking trazem o favorecido e o valor. Quatro formatos são reconhecidos:
autorização em lote ("Pendências"), demonstrativo DDA, comprovante de inclusão e comprovante individual.
"""
import datetime as dt
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

V = r"(\d{1,3}(?:\.\d{3})*,\d{2})"
EMPRESA = r"SUPERMERCADO[ .]*EXEMPLO"
TARIFA_BOLETO = 1.65
JANELA_DIAS = (-1, 4)  # débito no extrato entre 1 dia antes e 4 dias depois da data do comprovante


@dataclass
class Comprovante:
    arquivo: str
    formato: str
    data: dt.date
    favorecido: str
    valor: float
    desconto: float = 0.0


def _ascii(texto: str) -> str:
    texto = texto.replace("ﬁ", "fi").replace("ﬂ", "fl")
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def _num(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def _data(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%d/%m/%Y").date()


def texto_pdf(caminho) -> str:
    return _ascii("\n".join((p.extract_text() or "") for p in PdfReader(str(caminho)).pages))


def extrair(texto: str, arquivo: str = "") -> list[Comprovante]:
    out = []
    if "Autorizacoes >Pendencias" in texto:
        m = re.search(r"Por Data de Inclusao\s*(\d\d/\d\d/\d{4})", texto) or re.search(r"(\d\d/\d\d/\d{4})", texto)
        data, anterior = _data(m.group(1)), ""
        for linha in texto.split("\n"):
            m = re.match(r"(.*?)\s*4204-4907\S*\s+\d+\s+" + V + r"\s*$", linha)
            if m:
                nome = m.group(1)
                # nome quebrado em duas linhas: a primeira parte fica na linha anterior
                if anterior and not re.search(V + r"\s*$", anterior) and not anterior.startswith(
                        ("Favorecido", "INCLUIR", "PAGTO", "Produto", "Por Data")):
                    nome = anterior + " " + nome
                out.append(Comprovante(arquivo, "autorizacao", data, nome.strip(), _num(m.group(2))))
            anterior = linha.strip()
    elif "Titulos Eletronicos DDA" in texto:
        for m in re.finditer(r"(\d\d/\d\d/\d{4}) (\d\d/\d\d/\d{4}) (.+?) " + EMPRESA + r".*? " + V + " " + V, texto):
            doc, pagar = _num(m.group(4)), _num(m.group(5))
            out.append(Comprovante(arquivo, "dda", _data(m.group(2)), m.group(3).strip(), pagar,
                                   round(max(doc - pagar, 0.0), 2)))
    elif "Comprovante de inclusao" in texto:
        padrao = (r"Data do pagamento(\d\d/\d\d/\d{4}) Beneficiario original(.+?)(?:\s*Nosso|\n)"
                  r"[\s\S]*?Valor do doc R\$R\$ " + V + r" Valor a pagar R\$R\$ " + V)
        for m in re.finditer(padrao, texto):
            doc, pagar = _num(m.group(3)), _num(m.group(4))
            out.append(Comprovante(arquivo, "inclusao", _data(m.group(1)), m.group(2).strip(), pagar,
                                   round(max(doc - pagar, 0.0), 2)))
    else:
        m = re.search(r"(?:Beneficiario|Empresa)\n([\s\S]+?)\nData do (?:pagamento|agendamento)\n(\d\d/\d\d/\d{4})\n"
                      r"Valor nominal\nR\$ " + V + r"\nValor total a pagar\nR\$ " + V, texto)
        if m:
            desconto = re.search(r"Desconto\n" + V, texto)
            out.append(Comprovante(arquivo, "individual", _data(m.group(2)), m.group(1).replace("\n", " ").strip(),
                                   _num(m.group(4)), _num(desconto.group(1)) if desconto else 0.0))
    return out


def ler_pasta(pasta, ja_lidos: dict | None = None) -> tuple[list[Comprovante], list[str]]:
    """Lê todos os PDFs da pasta (e subpastas). Não move nem altera nada.

    `ja_lidos` = {hash: [Comprovante]} evita reler o mesmo arquivo. Devolve (comprovantes, arquivos não lidos).
    """
    comps, nao_lidos = [], []
    for pdf in sorted(Path(pasta).rglob("*.pdf")):
        h = hashlib.sha256(pdf.read_bytes()).hexdigest()
        if ja_lidos is not None and h in ja_lidos:
            comps += ja_lidos[h]
            continue
        achados = extrair(texto_pdf(pdf), str(pdf.relative_to(pasta)))
        if not achados:
            nao_lidos.append(str(pdf.relative_to(pasta)))
        if ja_lidos is not None:
            ja_lidos[h] = achados
        comps += achados
    for img in Path(pasta).rglob("*"):
        if img.suffix.lower() in (".png", ".jpg", ".jpeg"):
            nao_lidos.append(str(img.relative_to(pasta)) + " (imagem: precisa ser tratada à mão)")
    return comps, nao_lidos


def eh_titulo(descricao: str) -> bool:
    return "PAGAMENTO DE TITULO" in _ascii(descricao).upper()


def casar(lancamentos: list[dict], comprovantes: list[Comprovante]) -> dict:
    """Casa cada "PAGAMENTO DE TITULO" do extrato com um comprovante.

    Ordem de preferência: valor exato, valor + tarifa de 1,65 e valor com desconto, sempre dentro da
    janela de datas. Se dois comprovantes servem igualmente, não escolhe: devolve os candidatos.
    Retorno: {id do lançamento: {"comprovante": C | None, "regra": str, "candidatos": [C]}}.
    """
    titulos = [l for l in lancamentos if l["valor"] < 0 and eh_titulo(l["descricao"])]
    usados, resultado = set(), {}
    # Mesmo comprovante pode aparecer em dois PDFs (autorização e depois o DDA): elimina repetidos.
    unicos = {}
    for c in comprovantes:
        unicos.setdefault((c.data, round(c.valor, 2), c.favorecido[:12].upper()), c)
    comprovantes = list(unicos.values())
    for regra, ajuste in (("valor exato", lambda c: c.valor), ("valor + tarifa 1,65", lambda c: c.valor + TARIFA_BOLETO),
                          ("valor com desconto", lambda c: c.valor + c.desconto)):
        for l in titulos:
            if l["id"] in resultado and resultado[l["id"]]["comprovante"]:
                continue
            alvo = round(-l["valor"], 2)
            cand = [(abs((l["data"] - c.data).days), i, c) for i, c in enumerate(comprovantes)
                    if i not in usados and JANELA_DIAS[0] <= (l["data"] - c.data).days <= JANELA_DIAS[1]
                    and abs(round(ajuste(c), 2) - alvo) < 0.005 and (regra != "valor com desconto" or c.desconto)]
            if not cand:
                continue
            cand.sort(key=lambda x: x[0])
            melhores = [x for x in cand if x[0] == cand[0][0]]
            nomes = {x[2].favorecido[:12].upper() for x in melhores}
            if len(nomes) > 1:
                resultado[l["id"]] = {"comprovante": None, "regra": "ambíguo", "candidatos": [x[2] for x in melhores]}
                continue
            usados.add(melhores[0][1])
            resultado[l["id"]] = {"comprovante": melhores[0][2], "regra": regra, "candidatos": []}
    return resultado
