"""Gera a planilha de demonstração com dados fictícios (Demo/Fechamento Financeiro Exemplo 2026.xlsx).

    .venv\\Scripts\\python.exe scripts\\gerar_demo.py

Usa o plano de contas de Demo/estrutura.json e inventa lançamentos de janeiro a outubro: vendas diárias,
fornecedores, folha, impostos e despesas fixas. Sempre gera o mesmo resultado (semente fixa).
"""
import datetime as dt
import json
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from hoth.estrutura import Banco, Conta, Estrutura, Grupo  # noqa: E402
from hoth.modelo import GeradorPlanilha  # noqa: E402
from hoth.titulos import NOME_ARQUIVO, ArquivoTitulos, Carteira  # noqa: E402

DEMO = RAIZ / "Demo"
ANO, MESES = 2026, 10

FORNECEDORES = [  # (código, nome, conta, valor médio por compra, compras por mês)
    ("00101", "DISTRIBUIDORA ALFA LTDA", "FORNECEDOR EM GERAL", 4200, 8),
    ("00102", "PANIFICADORA BOM GRAO", "FORNECEDOR DA PADARIA", 1300, 6),
    ("00103", "LATICINIOS SERRA AZUL", "FORNECEDOR DE LATICINIOS", 2600, 6),
    ("00104", "FRIGORIFICO VALE VERDE", "FORNECEDOR DE AÇOUGUE", 5100, 6),
    ("00105", "BEBIDAS RIO CLARO", "FORNECEDOR DE BEBIDAS", 3800, 5),
    ("00106", "HORTIFRUTI DO CAMPO", "FORNECEDOR DE HORTIFRUTI", 1700, 10),
    ("00107", "ATACADO CENTRAL", "FORNECEDOR EM GERAL", 6900, 4),
]
FIXAS = [  # (descrição, conta, valor, dia)
    ("ALUGUEL - IMOBILIARIA EXEMPLO", "ALUGUEL IMÓVEL", 9500, 5),
    ("ENERGIA ELETRICA - CONCESSIONARIA", "ENERGIA ELÉTRICA", 7200, 12),
    ("AGUA E ESGOTO - SANEAMENTO", "ÁGUA E ESGOTO", 980, 15),
    ("CONTABILIDADE EXEMPLO", "CONTABILIDADE", 1800, 10),
    ("SISTEMA DE GESTAO", "SISTEMA (SISTEMA E GESTÃO)", 650, 10),
    ("INTERNET FIBRA", "INTERNET E DADOS", 320, 20),
    ("FOLHA DE PAGAMENTO", "SALÁRIOS (CLT)", 48000, 5),
    ("FGTS", "FGTS (CLT)", 3900, 7),
    ("INSS - GPS", "INSS (CLT)", 10600, 20),
    ("DAS - SIMPLES NACIONAL", "DAS - SIMPLES NACIONAL", 21000, 20),
    ("PROLABORE SOCIO A", "PROLABORE SÓCIO A", 6000, 5),
    ("PROLABORE SOCIO B", "PROLABORE SÓCIO B", 6000, 5),
    ("TARIFA PACOTE DE SERVICOS", "DESPESAS BANCÁRIAS", 189, 1),
]
PESO_DIA = [0.92, 0.85, 0.88, 0.95, 1.12, 1.38, 0.90]  # seg..dom


def estrutura() -> Estrutura:
    d = json.loads((DEMO / "estrutura.json").read_text(encoding="utf-8"))
    return Estrutura([Grupo(**g) for g in d["grupos"]], [Conta(**c) for c in d["contas"]],
                     [Banco(**b) for b in d["bancos"]], empresa="SUPERMERCADO EXEMPLO LTDA", ano=ANO)


def lancamentos(rnd: random.Random) -> list[dict]:
    lancs = []

    def add(banco, data, desc, valor, conta, doc=""):
        lancs.append({"id": f"DEMO-{len(lancs) + 1:05d}", "banco": banco, "data": data, "descricao": desc,
                      "documento": doc, "valor": round(valor, 2), "conta": conta, "origem": "Demonstração",
                      "referencia": "", "observacao": "", "importado_em": None})

    for mes in range(1, MESES + 1):
        dia = dt.date(ANO, mes, 1)
        sazonal = 1 + 0.04 * (mes in (3, 5, 10)) - 0.03 * (mes == 2)
        while dia.month == mes:
            venda = 19500 * PESO_DIA[dia.weekday()] * sazonal * rnd.uniform(0.9, 1.1)
            add("Santander", dia, "RECEBIMENTO CARTOES - ADQUIRENTE", venda * 0.68, "RECEITA DE VENDAS DE MERCADORIA")
            add("Caixa Loja", dia, "VENDAS EM DINHEIRO", venda * 0.22, "RECEITA DE VENDAS DE MERCADORIA")
            add("Cora", dia, "PIX RECEBIDOS", venda * 0.10, "RECEITA DE VENDAS DE MERCADORIA")
            dia += dt.timedelta(days=1)
        for cod, nome, conta, media, vezes in FORNECEDORES:
            for _ in range(vezes):
                d = dt.date(ANO, mes, rnd.randint(1, 28))
                banco = rnd.choice(["Santander", "Santander", "Cora", "Caixa Loja"])
                add(banco, d, f"PAGTO BOLETO {cod} - {nome}", -media * rnd.uniform(0.7, 1.3), conta,
                    f"{rnd.randint(100000, 999999)}")
        for desc, conta, valor, d in FIXAS:
            add("Santander", dt.date(ANO, mes, d), desc, -valor * rnd.uniform(0.97, 1.03), conta)
        add("Santander", dt.date(ANO, mes, 25), "APLICACAO CDB", -15000, "APLICAÇÃO")
        add("Santander CDB", dt.date(ANO, mes, 25), "APLICACAO CDB", 15000, "APLICAÇÃO")
    return sorted(lancs, key=lambda l: (l["data"], l["banco"]))


def carteira(lancs: list[dict], rnd: random.Random) -> Carteira:
    """Títulos do contas a pagar: os boletos pagos de setembro/outubro, alguns vencidos e os de novembro."""
    c = Carteira()
    hoje = dt.date(ANO, 10, 30)

    def titulo(cod, nome, conta, venc, valor, doc):
        c.titulos.append({"id": f"T{len(c.titulos) + 1:04d}", "codigo": cod, "fornecedor": f"{cod} - {nome}",
                          "documento": doc, "parcela": "1", "duplicata": doc, "compra": venc - dt.timedelta(days=21),
                          "vencimento": venc, "valor": round(valor, 2), "banco_ret": "", "cobranca": "BOLETO",
                          "conta": conta, "no_ret": "Sim", "primeira_importacao": hoje, "ultima_vez_ret": hoje})

    nomes = {f[0]: f for f in FORNECEDORES}
    for l in lancs:
        if l["documento"] and l["data"].month >= 9:
            cod = l["descricao"].split()[2]
            titulo(cod, nomes[cod][1], nomes[cod][2], l["data"], -l["valor"], l["documento"])
    for cod, nome, conta, media, vezes in FORNECEDORES:
        for _ in range(vezes):
            venc = hoje + dt.timedelta(days=rnd.randint(-6, 30))
            titulo(cod, nome, conta, venc, media * rnd.uniform(0.7, 1.3), f"{rnd.randint(100000, 999999)}")
    c.categorias = [{"codigo": cod, "fornecedor": nome, "categoria": "MERCADORIA", "atualizado_em": hoje}
                    for cod, nome, *_ in FORNECEDORES]
    c.entradas = [{"id": f"E{i:03d}", "data": hoje + dt.timedelta(days=i),
                   "descricao": "Recebimento previsto de vendas",
                   "valor": round(19500 * PESO_DIA[(hoje + dt.timedelta(days=i)).weekday()], 2), "forma": "Vendas"}
                  for i in range(1, 32)]
    return c


def main():
    rnd = random.Random(2026)
    lancs = lancamentos(rnd)
    vendas = {m: sum(l["valor"] for l in lancs if l["data"].month == m and l["valor"] > 0
                     and l["conta"] == "RECEITA DE VENDAS DE MERCADORIA") for m in range(1, MESES + 1)}
    dre_manual = [{"ano": ANO, "mes": m, "conta": "FATURAMENTO - VENDAS REALIZADAS", "valor": round(v, 2)}
                  for m, v in vendas.items()]
    orcamento = [{"ano": ANO, "mes": m, "conta": "FATURAMENTO - VENDAS REALIZADAS", "valor": 620000}
                 for m in range(1, 13)]
    agora = dt.datetime(ANO, 10, 30, 17, 0)
    auditoria = [[agora, "Demonstração", "Planilha gerada com dados fictícios", len(lancs), "", ""]]
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else DEMO
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / "Fechamento Financeiro Exemplo 2026.xlsx"
    GeradorPlanilha(estrutura()).gerar(destino, lancamentos=lancs, ajustes=[], orcamento=orcamento, saldos=[],
                                       auditoria=auditoria, meses_fechados=MESES, dre_manual=dre_manual)
    ArquivoTitulos(pasta / NOME_ARQUIVO, pasta / "BKP").gravar(carteira(lancs, rnd), "Demonstração", "dados fictícios")
    print(f"{len(lancs)} lançamentos fictícios -> {destino}")


if __name__ == "__main__":
    main()
