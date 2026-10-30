"""Classificação automática dos lançamentos importados, aprendida com o histórico da planilha.

Regras, da mais forte para a mais fraca:
1. Descrição exata já classificada antes (mesmo banco e mesmo sentido: entrada ou saída).
2. Tipo de operação muito consistente (ex.: "PIX RECEBIDO" +, "PIX DEVOLVIDO" −): vale mais que o nome,
   porque a mesma pessoa pode pagar uma compra e receber uma troca de cartão.
3. Fornecedor: nome do favorecido (do comprovante, no PAGAMENTO DE TITULO, ou da própria descrição)
   já classificado antes em qualquer banco, no mesmo sentido.
4. Tipo de operação consistente.

Boletos cedidos a factoring/fundos ("FOMENTO", "MULTICREDITO"...) não identificam o fornecedor:
nunca são classificados sozinhos, só recebem sugestões.

Só classifica sozinho quando o histórico é consistente. O resto vai para revisão com sugestões.

Acima de tudo vêm as regras fixas por código de fornecedor da Caixa Loja ("00487 - ..."), decididas pelo
usuário quando o histórico está dividido entre contas: conta preenchida classifica sempre; conta vazia manda
sempre para revisão, mesmo com histórico consistente.
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .comprovantes import eh_titulo
from .texto import chave

# Prefixos que antecedem o nome da contraparte na descrição.
PREFIXOS = [
    "PAGAMENTO DE BOLETO OUTROS BANCOS", "PAGAMENTO DE BOLETO", "PAGAMENTO A FORNECEDORES", "PGTO FORNEC",
    "PIX RECEBIDO", "PIX ENVIADO", "PIX AGENDADO", "PIX DEVOLVIDO", "TED RECEBIDA", "TED ENVIADA",
    "TRANSF PIX RECEBIDA", "TRANSF PIX ENVIADA", "BOLETO PAGO", "PGTO QR CODE PIX",
]
SUFIXOS_EMPRESA = r"\b(LTDA|LIMITADA|EIRELI|EPP|ME|S ?/? ?A|CIA|COMERCIO|COM|DISTRIBUIDORA|DISTRIB|IND|INDUSTRIA|E|DE|DA|DO|DOS|DAS)\b"
TAM_CHAVE_NOME = 16

MIN_EXATA, PCT_EXATA = 1, 0.95
MIN_NOME, PCT_NOME = 2, 0.90
MIN_TIPO, PCT_TIPO = 20, 0.97
MIN_TIPO_FORTE, PCT_TIPO_FORTE = 50, 0.995
INTERMEDIARIOS = re.compile(r"FOMENTO|FACTORING|MULTICREDITO|FIDC|SECURITIZ|FUNDO DE INVEST|\bBANCO\b|FINANCE|CREDITO")


def chave_regra_descricao(descricao: str) -> str:
    """Chave de uma regra fixa por descrição no Regras fixas.json (ao lado das chaves por código de fornecedor)."""
    return "desc:" + chave(descricao) if chave(descricao) else ""


def codigo_fornecedor(descricao: str) -> str:
    m = re.match(r"^(\d{3,6}) - ", chave(descricao))
    return m.group(1) if m else ""


def nome_contraparte(descricao: str) -> str:
    d = chave(descricao)
    d = re.sub(r"^\d{3,6} - ", "", d)  # Caixa Loja: "00038 - IRMAOS KUHL LTDA"
    for p in PREFIXOS:
        if d.startswith(p):
            return d[len(p):].strip()
    return ""


def chave_nome(nome: str) -> str:
    """Chave curta para comparar nomes de fornecedor vindos de fontes diferentes (extrato corta em 25
    caracteres, PDF às vezes junta palavras)."""
    n = re.sub(SUFIXOS_EMPRESA, " ", chave(nome))
    n = re.sub(r"[^A-Z0-9]", "", n)
    return n[:TAM_CHAVE_NOME] if len(n) >= 6 else ""


def tipos(l: dict) -> list[str]:
    palavras = re.sub(r"[\d.,/-]+", " ", chave(l["descricao"])).split()
    sinal = "+" if l["valor"] > 0 else "-"
    return [f"{l['banco']}|{' '.join(palavras[:k])}|{sinal}" for k in (3, 2) if len(palavras) >= k]


@dataclass
class Resultado:
    conta: str = ""
    regra: str = ""          # exata | fornecedor | tipo | "" (pendente)
    confianca: str = ""      # alta | média | ""
    sugestoes: list = field(default_factory=list)  # [(conta, motivo)]
    favorecido: str = ""


class Classificador:
    def __init__(self, historico: list[dict], titulos_identificados: dict | None = None,
                 regras_fixas: dict | None = None):
        """`historico`: lançamentos já classificados (banco, descricao, valor, conta).
        `titulos_identificados`: {id: favorecido} de PAGAMENTO DE TITULO antigos casados com comprovante,
        para aprender fornecedor -> conta também a partir deles.
        `regras_fixas`: {código do fornecedor: conta ("" = sempre revisar)}."""
        self.regras_fixas = regras_fixas or {}
        self.exata = defaultdict(Counter)
        self.nome = defaultdict(Counter)
        self.tipo = defaultdict(Counter)
        titulos_identificados = titulos_identificados or {}
        for l in historico:
            if not l.get("conta"):
                continue
            titulo = eh_titulo(l["descricao"])
            if not titulo:
                self.exata[(l["banco"], chave(l["descricao"]), l["valor"] > 0)][l["conta"]] += 1
                for t in tipos(l):
                    self.tipo[t][l["conta"]] += 1
            favorecido = titulos_identificados.get(l.get("id")) if titulo else nome_contraparte(l["descricao"])
            k = chave_nome(favorecido or "")
            if k:
                self.nome[(k, l["valor"] > 0)][l["conta"]] += 1

    @staticmethod
    def _consistente(contagem: Counter, minimo: int, pct: float):
        if not contagem:
            return None
        conta, n = contagem.most_common(1)[0]
        total = sum(contagem.values())
        return conta if total >= minimo and n / total >= pct else None

    def classificar(self, l: dict, favorecido: str = "") -> Resultado:
        # Regra por descrição exata ("desc:...") vale antes da regra por código de fornecedor.
        for k, quem in ((chave_regra_descricao(l["descricao"]), "descrição"), (codigo_fornecedor(l["descricao"]), "fornecedor")):
            if k and k in self.regras_fixas:
                if self.regras_fixas[k]:
                    return Resultado(self.regras_fixas[k], "fixa", "alta", [], favorecido)
                r = self._pelo_historico(l, favorecido)
                proposta = [(r.conta, f"{r.regra} ({quem} marcado para sempre revisar)")] if r.conta else []
                return Resultado("", "", "", (proposta + r.sugestoes)[:3], favorecido)
        return self._pelo_historico(l, favorecido)

    def _pelo_historico(self, l: dict, favorecido: str = "") -> Resultado:
        sugestoes = Counter()
        titulo = eh_titulo(l["descricao"])
        nome = favorecido or nome_contraparte(l["descricao"])
        intermediario = bool(INTERMEDIARIOS.search(chave(nome))) if nome else False

        def achou(conta, regra, confianca):
            if intermediario:  # factoring/fundo: só sugere
                sugestoes[(conta, f"{regra} (boleto de factoring/fundo, conferir)")] += 1000
                return None
            return Resultado(conta, regra, confianca, [], favorecido)

        if not titulo:
            ex = self.exata.get((l["banco"], chave(l["descricao"]), l["valor"] > 0))
            conta = self._consistente(ex, MIN_EXATA, PCT_EXATA)
            if conta and (r := achou(conta, "exata", "alta" if sum(ex.values()) >= 2 else "média")):
                return r
            for c, q in (ex or {}).items():
                sugestoes[(c, "mesma descrição")] += q
            for t in tipos(l):
                conta = self._consistente(self.tipo.get(t), MIN_TIPO_FORTE, PCT_TIPO_FORTE)
                if conta and (r := achou(conta, "tipo", "alta")):
                    return r
        k = chave_nome(nome) if nome else ""
        if k:
            cont = self.nome.get((k, l["valor"] > 0))
            conta = self._consistente(cont, MIN_NOME, PCT_NOME)
            if conta and (r := achou(conta, "fornecedor",
                                     "alta" if favorecido or sum(cont.values()) >= 5 else "média")):
                return r
            for c, q in (cont or {}).items():
                sugestoes[(c, f"fornecedor {nome[:30]}")] += q
        if not titulo:
            for t in tipos(l):
                cont = self.tipo.get(t)
                conta = self._consistente(cont, MIN_TIPO, PCT_TIPO)
                if conta and (r := achou(conta, "tipo", "média")):
                    return r
                for c, q in (cont or {}).items():
                    sugestoes[(c, "mesmo tipo de operação")] += q / 100  # pesa menos que nome e descrição
        return Resultado("", "", "", [s for s, _ in sugestoes.most_common(3)], favorecido)
