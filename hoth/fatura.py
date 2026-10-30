"""Fatura do cartão de crédito (Santander Empresas Mastercard, PDF com senha).

O extrato traz uma linha só (`DEBITO AUT. FAT.CARTAO MASTER CARD FINAL 0000`); a fatura traz as compras. Abrir a
fatura = trocar essa linha pelas compras, cada uma com a sua conta, na data do débito (decisão de 27/10/2026).

A descrição de cada compra segue o que já estava na Hoth (faturas abertas à mão): nome do estabelecimento sem a
cidade, com a parcela no fim ("PRONTO *M G S DISTRIBU PARC 02/05"), para o classificador reconhecer.
"""
import datetime as dt
import hashlib
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

from .texto import chave, id_lancamento, limpar

V = r"-?\d{1,3}(?:\.\d{3})*,\d{2}"
DEBITO = re.compile(r"FAT\.?\s*CARTAO", re.I)   # "DEBITO AUT. FAT.CARTAO MASTER CARD FINAL 0000"
JANELA_DEBITO = (0, 10)                          # dias depois do vencimento em que o débito aparece no extrato
# Cidades que a fatura cola depois do nome do estabelecimento (sem acento, maiúsculas).
CIDADES = ["SAO PAULO", "RIO DE JANEIRO", "RIO DE JANEIR", "RIO DE JANEI", "SAN FRANCISCO", "RIBEIRO PRETO",
           "LIMEIRA", "GUARULHOS", "OSASCO", "SHERIDAN", "HORTOLANDIA", "HORTOLNDIA", "CAMPINAS", "PIRACICABA",
           "AMERICANA", "BARUERI", "CURITIBA"]
IGNORAR = re.compile(r"^(DEB\s+AUTOM\s+DE\s+FATURA|ANUIDADE)", re.I)


class SenhaFatura(Exception):
    pass


def _num(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def texto_pdf(caminho, senha: str = "") -> str:
    r = PdfReader(str(caminho))
    if r.is_encrypted and not r.decrypt(senha or ""):
        raise SenhaFatura(f"{Path(caminho).name}: senha da fatura incorreta (senha_fatura no hoth.json)")
    return "\n".join((p.extract_text() or "") for p in r.pages)


def _sem_cidade(nome: str) -> str:
    nome = limpar(nome)
    for cidade in sorted(CIDADES, key=len, reverse=True):
        m = re.search(r"\s*" + r"\s*".join(map(re.escape, cidade.split())) + r"\s*$", chave(nome))
        if m and m.start() > 0:
            return limpar(nome[:m.start()])
    return nome


def descricao_item(bruta: str) -> str:
    """'ASSAI ATACADISTA LJ246 LIMEIRA\\' -> 'ASSAI ATACADISTA LJ246';
    'PRONTO *M G S DISTRIBU PARC  02/05SAO PAULO\\' -> 'PRONTO *M G S DISTRIBU PARC 02/05'."""
    texto = bruta.split("\\")[0]
    parc = re.search(r"\s*PARC\s+(\d\d/\d\d)", texto)
    if parc:
        return f"{_sem_cidade(texto[:parc.start()])} PARC {parc.group(1)}"
    return _sem_cidade(texto)


def ler_fatura(caminho, senha: str = "", texto: str | None = None) -> dict:
    t = texto if texto is not None else texto_pdf(caminho, senha)
    m = re.search(r"Data de Vencimento:\s*(\d\d/\d\d/\d{4})", t)
    if not m or "FATURA MENSAL" not in t.upper():
        raise ValueError(f"{Path(caminho).name}: não parece uma fatura de cartão (vencimento não encontrado)")
    venc = dt.datetime.strptime(m.group(1), "%d/%m/%Y").date()
    fech = re.search(r"Data do Fechamento da Fatura:\s*(\d\d/\d\d/\d{4})", t)
    total = re.search(r"Total de compras desta Fatura \(R\$ \+ US\$\)\s*(" + V + ")", t)
    cartao = re.search(r"(\d{4}) XXXX XXXX (\d{4})", t)
    itens, internacional, linhas = [], False, t.split("\n")
    i = 0
    while i < len(linhas):
        ln = linhas[i]
        if "Transações Internacionais" in ln:
            internacional = True
        elif "Transações Nacionais" in ln:
            internacional = False
        m = re.match(r"^(\d\d-\d\d-\d{4}) (.+)$", ln)
        if m:
            corpo, j = m.group(2), i
            while not re.search(V + r"\s*$", corpo) and j + 1 < len(linhas) and j - i < 3:   # linha quebrada
                j += 1
                corpo += " " + linhas[j].strip()
            valores = re.findall(V, corpo)
            if valores:
                if internacional and len(valores) >= 3:            # US$ | sigla | R$ | cotação
                    valor, bruta = _num(valores[-2]), corpo[:corpo.find(valores[0])]
                else:
                    valor, bruta = _num(valores[-1]), corpo[:corpo.rfind(valores[-1])]
                desc = descricao_item(bruta)
                if not IGNORAR.match(chave(desc)) and valor > 0:
                    itens.append({"data_compra": dt.datetime.strptime(m.group(1), "%d-%m-%Y").date(),
                                  "descricao": desc, "valor": round(valor, 2), "texto_fatura": limpar(bruta)})
            i = j
        i += 1
    # O débito é o "Total" a pagar = compras + saldo da fatura anterior (ex.: crédito de 0,02 pago a mais antes).
    a_pagar = re.search(r"Despesas/D[ée]bitos\s*(" + V + r")\s*=\s*Total\s*(" + V + ")", t)
    saldo = re.search(r"Saldo\s*(" + V + r")\s*\+", t)
    if saldo and abs(_num(saldo.group(1))) >= 0.005:
        valor_saldo = _num(saldo.group(1))
        itens.append({"data_compra": venc, "descricao": "SALDO DA FATURA ANTERIOR", "valor": round(valor_saldo, 2),
                      "texto_fatura": f"Saldo {saldo.group(1)} (pago a mais ou a menos na fatura anterior)"})
    soma = round(sum(x["valor"] for x in itens), 2)
    compras = _num(total.group(1)) if total else soma
    return {"arquivo": str(caminho), "vencimento": venc,
            "fechamento": dt.datetime.strptime(fech.group(1), "%d/%m/%Y").date() if fech else None,
            "total": _num(a_pagar.group(2)) if a_pagar else compras, "compras": compras, "soma_itens": soma,
            "cartao": f"final {cartao.group(2)}" if cartao else "", "itens": itens}


def agrupar(itens: list[dict]) -> list[dict]:
    """Uma linha por estabelecimento (parcelas e compras do mesmo lugar somadas)."""
    grupos = defaultdict(list)
    for x in itens:
        grupos[chave(re.sub(r"\s*PARC \d\d/\d\d$", "", x["descricao"]))].append(x)
    saida = []
    for xs in grupos.values():
        nome = re.sub(r"\s*PARC \d\d/\d\d$", "", xs[0]["descricao"])
        saida.append({"data_compra": min(x["data_compra"] for x in xs), "descricao": nome,
                      "valor": round(sum(x["valor"] for x in xs), 2),
                      "texto_fatura": "; ".join(f"{x['data_compra']:%d/%m} {x['descricao']} {x['valor']:.2f}" for x in xs)})
    return saida


def achar_debito(fatura: dict, lancamentos: list[dict], ja_abertos: set[str] = frozenset()) -> list[dict]:
    """Linhas do Santander com o débito automático da fatura: mesmo valor do total, até 10 dias após o vencimento."""
    v = fatura["vencimento"]
    return [l for l in lancamentos if l.get("banco") == "Santander" and l.get("data") and l["id"] not in ja_abertos
            and DEBITO.search(str(l.get("descricao") or "")) and abs(-float(l["valor"] or 0) - fatura["total"]) < 0.005
            and JANELA_DEBITO[0] <= (l["data"] - v).days <= JANELA_DEBITO[1]]


OPERACAO_BANCARIA = re.compile(r"^(PIX|TED|DOC|PAGAMENTO|PGTO|TARIFA|DEBITO|APLICACAO|RESGATE|TRANSF|CONTA DE|"
                               r"BOLETO|COMPRA CARTAO|IOF SOBRE|JUROS|SAQUE|CHEQUE)", re.I)


def aberta_a_mao(fatura: dict, lancamentos: list[dict]) -> dict | None:
    """Fatura já aberta antes do app (à mão): num dia perto do vencimento, as saídas do Santander que não são
    operações bancárias somam o total da fatura. Devolve {data, linhas} ou None."""
    v = fatura["vencimento"]
    por_dia = defaultdict(list)
    for l in lancamentos:
        if l.get("banco") == "Santander" and l.get("data") and (l.get("valor") or 0) < 0 \
                and -1 <= (l["data"] - v).days <= JANELA_DEBITO[1] and not OPERACAO_BANCARIA.match(str(l["descricao"])):
            por_dia[l["data"]].append(l)
    alvos = {fatura["total"], fatura.get("compras", fatura["total"])}   # à mão, às vezes sem o saldo de centavos
    for d, ls in sorted(por_dia.items()):
        soma = -sum(l["valor"] for l in ls)
        if any(abs(soma - a) < 0.05 for a in alvos):
            return {"data": d, "linhas": len(ls)}
    return None


def itens_como_lancamentos(itens: list[dict], debito: dict) -> list[dict]:
    """Compras como lançamentos do Santander na data do débito (ID no mesmo formato dos extratos)."""
    ocorr, saida = defaultdict(int), []
    for x in itens:
        k = (round(x["valor"], 2), chave(x["descricao"]))
        ocorr[k] += 1
        saida.append({"id": id_lancamento("Santander", debito["data"], -x["valor"], x["descricao"], "", ocorr[k]),
                      "banco": "Santander", "data": debito["data"], "descricao": x["descricao"], "documento": "",
                      "valor": -round(x["valor"], 2), "data_compra": x["data_compra"], "texto_fatura": x["texto_fatura"]})
    return saida


def chave_estabelecimento(descricao) -> str:
    """Começo do nome, só letras e números: aproxima 'TOKIO MARINE*AUTO07D10' e 'TOKIO MARINE AUTO07/D10'."""
    texto = re.sub(r"\s*PARC \d\d/\d\d$", "", chave(descricao))
    return re.sub(r"[^A-Z0-9]", "", texto)[:10]


def classificar_itens(itens: list[dict], historico: list[dict], classificador) -> None:
    """Conta proposta para cada compra: o classificador do Hoth (descrição igual à de faturas já abertas, regras) e,
    se ele não decidir, a conta mais usada para o mesmo estabelecimento no Santander (pelo começo do nome)."""
    por_estab = defaultdict(lambda: defaultdict(int))
    for l in historico:
        if l.get("banco") == "Santander" and (l.get("valor") or 0) < 0 and l.get("conta"):
            k = chave_estabelecimento(l["descricao"])
            if len(k) >= 5:
                por_estab[k][l["conta"]] += 1
    for x in itens:
        r = classificador.classificar({"banco": "Santander", "descricao": x["descricao"], "valor": -x["valor"]})
        x.update(proposta=r.conta, regra=r.regra, confianca=r.confianca, sugestoes=[s[0] for s in r.sugestoes])
        if r.conta:
            continue
        votos = por_estab.get(chave_estabelecimento(x["descricao"]))
        if votos:
            conta, n = max(votos.items(), key=lambda kv: kv[1])
            if n / sum(votos.values()) >= 0.8:
                x.update(proposta=conta, regra="estabelecimento", confianca="alta" if n >= 2 else "média")
            else:
                x["sugestoes"] = [c for c, _ in sorted(votos.items(), key=lambda kv: -kv[1])][:3]


def listar_pdfs(pasta) -> list[Path]:
    """PDFs de fatura na pasta (e subpastas): nome com "fatura"."""
    pasta = Path(pasta)
    if not pasta.exists():
        return []
    return sorted((p for p in pasta.rglob("*") if p.suffix.lower() == ".pdf" and "fatura" in p.name.lower()),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def sha256(caminho) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()
