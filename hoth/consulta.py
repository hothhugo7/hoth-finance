"""Busca de títulos em aberto para cada valor digitado da fita do malote."""
import datetime as dt

from .conciliacao import PAGOS, SITUACOES


def candidatos_malote(valor: float, envio: dt.date, titulos: list[dict], resultado: dict,
                      ja_escolhidos: set[str] = frozenset(), em_outro_malote: dict | None = None) -> list[dict]:
    """Títulos em aberto com esse valor, do vencimento mais próximo do envio para o mais distante."""
    em_outro_malote = em_outro_malote or {}
    valor = round(valor, 2)
    saida = []
    for t in titulos:
        if abs(float(t["valor"] or 0) - valor) >= 0.005 or t["id"] in ja_escolhidos:
            continue
        sit = resultado.get(t["id"], {}).get("situacao", "")
        if sit in PAGOS or sit in ("cancelado", "aguardando_fatura"):
            continue
        r = resultado.get(t["id"], {})
        saida.append({"id": t["id"], "fornecedor": t["fornecedor"], "documento": t["documento"],
                      "parcela": t["parcela"], "vencimento": t["vencimento"], "valor": t["valor"],
                      "situacao_texto": SITUACOES.get(r.get("situacao", ""), ""),
                      "outro_malote": em_outro_malote.get(t["id"], "")})
    saida.sort(key=lambda t: (bool(t["outro_malote"]), abs((t["vencimento"] - envio).days)))
    return saida
