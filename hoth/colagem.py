"""Lançamentos da Caixa Loja colados do CONTROLE DE CAIXA.

O usuário copia linhas do CONTROLE (DATA | MÊS | DESCRIÇÃO | PLANO DE CONTAS | ENTRADA | SAÍDA | SALDO, com ou
sem MÊS e SALDO) e cola no app. `interpretar()` lê o texto colado (tabulado, como o Excel copia), confere cada
linha e marca o que já está na planilha; o usuário corrige na tela; `registros()` monta o que será gravado.

O ID segue a regra do histórico migrado (banco, data, valor, descrição, ocorrência no dia), para reconhecer
lançamentos que já foram colados antes.
"""
import datetime as dt
import re
from collections import Counter, defaultdict

from .texto import chave, id_lancamento, limpar

BANCO = "Caixa Loja"
LOTERICA = re.compile(r"LOTERIC")


def _data(texto) -> dt.date | None:
    t = limpar(texto)
    if re.fullmatch(r"4\d{4}", t):   # célula sem formato de data: número de série do Excel
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(t))
    for formato in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(t, formato).date()
        except ValueError:
            pass
    return None


def valor_br(texto) -> float | None:
    """ "R$ 1.952,05" -> 1952.05; vazio ou "R$ -" -> 0; texto que não é valor -> None."""
    t = re.sub(r"R\$|\s", "", str(texto or ""))
    if t in ("", "-"):
        return 0.0
    negativo = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    if not re.fullmatch(r"-?\d+(\.\d{1,2})?", t):
        return None
    return -float(t) if negativo else float(t)


def _colunas(celulas: list[str]) -> list[str]:
    """Devolve [data, descrição, plano, entrada, saída], com ou sem a coluna MÊS."""
    c = celulas + [""] * 7
    if re.fullmatch(r"\d{1,2}", c[1].strip()):
        return [c[0], c[2], c[3], c[4], c[5]]
    return [c[0], c[1], c[2], c[3], c[4]]


def interpretar(texto: str, contas: list[str], ids_existentes: set[str], caixa_existente: list[dict] = (),
                desde: dt.date | None = None) -> list[dict]:
    """`caixa_existente`: lançamentos da Caixa Loja já na planilha (id, data, valor, descricao), para achar
    correções. `desde`: linhas anteriores ficam de fora; anos anteriores nem aparecem."""
    validas = {chave(c): c for c in contas}
    linhas = []
    for n, bruta in enumerate(texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"), start=1):
        celulas = bruta.split("\t")
        if not any(c.strip() for c in celulas) or chave(celulas[0]) == "DATA":
            continue
        data, descricao, plano, entrada, saida = _colunas(celulas)
        avisos = []
        d = _data(data)
        if not d and not limpar(descricao):
            continue   # linhas soltas da aba copiada inteira: SALDO no topo, linhas em branco no fim
        ano = d.year if d else int((re.findall(r"(?<!\d)(\d{4})(?!\d)", data) or ["9999"])[-1])
        if desde and ano < desde.year:
            continue   # anos anteriores: nem aparecem
        if valor_br(entrada) == 0 and valor_br(saida) == 0:
            continue   # linha preparada sem valor (ex.: "fechamento caixa 5" ainda vazio)
        if not d:
            avisos.append(f"data inválida: {data.strip() or '(vazia)'}")
        elif not dt.date(2020, 1, 1) <= d <= dt.date.today() + dt.timedelta(days=31):
            avisos.append(f"data fora do esperado: {d:%d/%m/%Y}")
        ent, sai = valor_br(entrada), valor_br(saida)
        for nome, bruto, v in (("entrada", entrada, ent), ("saída", saida, sai)):
            if v is None:
                avisos.append(f"{nome} inválida: {bruto.strip()}")
        valor = round((ent or 0) - (sai or 0), 2)
        if valor == 0 and ent is not None and sai is not None:
            avisos.append("sem valor")
        conta = validas.get(chave(plano), "")
        if limpar(plano) and not conta:
            avisos.append(f"conta não existe no plano: {limpar(plano)}")
        linhas.append({"linha": n, "data": d, "descricao": limpar(descricao), "plano_original": limpar(plano),
                       "conta": conta, "valor": valor, "avisos": avisos,
                       "loterica": bool(LOTERICA.search(chave(descricao)))})
    for l, i in zip(linhas, ids(linhas)):
        l["id"] = i
        l["ja_existe"] = bool(i) and i in ids_existentes
        l["fora_periodo"] = bool(desde and l["data"] and l["data"] < desde)
    # Lançamento da Hoth que sumiu do CONTROLE: a linha nova do mesmo dia com a mesma descrição (valor mudou) ou o
    # mesmo valor (descrição mudou) provavelmente é a correção dele. Um para um: cada sumido aponta só para a linha
    # mais parecida, porque há várias "troca cartão" no mesmo dia. Boletos do RET ("00025 - ...") não estão no
    # CONTROLE e ficam de fora.
    # Só nos dias em que a colagem trouxe também o que já estava gravado: colando só um trecho do dia, o resto
    # pareceria sumido.
    colados = {l["id"] for l in linhas}
    dias_completos = {l["data"] for l in linhas if l["ja_existe"]}
    novas = defaultdict(list)
    for l in linhas:
        l["correcao_de"] = ""
        if l["data"] in dias_completos and not l["ja_existe"] and not l["fora_periodo"]:
            novas[l["data"]].append(l)
    for e in sorted(caixa_existente, key=lambda e: (e["data"], e["id"])):
        if e["id"] in colados or e["data"] not in novas or re.match(r"^\d{3,6} - ", str(e["descricao"])):
            continue
        mesma_desc = lambda l: chave(l["descricao"]) == chave(e["descricao"])
        candidatas = [l for l in novas[e["data"]] if not l["correcao_de"]
                      and (mesma_desc(l) or l["valor"] == round(e["valor"], 2))]
        if candidatas:
            l = min(candidatas, key=lambda l: (not mesma_desc(l), abs(l["valor"] - e["valor"])))
            l["correcao_de"] = f"{e['descricao']} ({e['valor']:.2f})"
    for l in linhas:
        # Já na planilha, fora do período, lotérica (vem do RET) e possível correção ficam de fora até o usuário marcar.
        l["incluir"] = not (l["ja_existe"] or l["fora_periodo"] or l["loterica"] or l["correcao_de"]) and not any(
            a.startswith(("data", "entrada", "saída", "sem valor")) for a in l["avisos"])
    return linhas


def ids(linhas: list[dict], ids_existentes: set[str] = frozenset(), forcar: set[int] = frozenset()) -> list[str]:
    """IDs na ordem colada. Linhas em `forcar` (índices) são lançamentos repetidos de propósito: recebem a
    próxima ocorrência livre, para não colidir com o que já está na planilha."""
    ocorrencias, saida = Counter(), []
    for i, l in enumerate(linhas):
        if not l.get("data"):
            saida.append("")
            continue
        k = (l["data"], round(l["valor"], 2), chave(l["descricao"]))
        ocorrencias[k] += 1
        novo = id_lancamento(BANCO, l["data"], l["valor"], l["descricao"], "", ocorrencias[k])
        while i in forcar and novo in ids_existentes:
            ocorrencias[k] += 1
            novo = id_lancamento(BANCO, l["data"], l["valor"], l["descricao"], "", ocorrencias[k])
        saida.append(novo)
    return saida


def registros(linhas: list[dict], contas: list[str], ids_existentes: set[str]) -> list[dict]:
    """Linhas revisadas na tela (data ISO ou date, descrição, conta, valor, incluir, ja_existe) -> registros
    para `PlanilhaEmUso.gravar_lancamentos`. Erros impedem a gravação inteira."""
    validas = {chave(c): c for c in contas}
    erros, todas = [], []
    for l in linhas:
        d = l["data"] if isinstance(l["data"], dt.date) else _data(l.get("data") or "")
        r = {**l, "data": d, "descricao": limpar(l.get("descricao")), "valor": round(float(l.get("valor") or 0), 2)}
        todas.append(r)
        if not r["incluir"]:
            continue
        rotulo = f"linha {l.get('linha', '?')}"
        if not d:
            erros.append(f"{rotulo}: data inválida")
        if not r["descricao"]:
            erros.append(f"{rotulo}: descrição vazia")
        if not r["valor"]:
            erros.append(f"{rotulo}: sem valor")
        if l.get("conta") and chave(l["conta"]) not in validas:
            erros.append(f"{rotulo}: conta não existe: {l['conta']}")
        r["conta"] = validas.get(chave(l.get("conta")), "")
    if erros:
        raise ValueError("Corrija antes de gravar: " + "; ".join(erros))
    # Ocorrências contadas sobre tudo o que foi colado (também o que ficou de fora), igual à prévia.
    forcar = {i for i, r in enumerate(todas) if r["incluir"] and r.get("ja_existe")}
    out = []
    for r, i in zip(todas, ids(todas, ids_existentes, forcar)):
        if not r["incluir"]:
            continue
        obs = [] if chave(r.get("plano_original")) in ("", chave(r["conta"])) else [
            f"No CONTROLE: {r['plano_original']}"]
        out.append({"id": i, "banco": BANCO, "data": r["data"], "descricao": r["descricao"], "documento": "",
                    "valor": r["valor"], "conta": r["conta"],
                    "origem": "Colagem Caixa Loja: " + ("revisada" if r["conta"] else "pendente de revisão"),
                    "referencia": "CONTROLE DE CAIXA (colado)", "observacao": " | ".join(obs)})
    return out
