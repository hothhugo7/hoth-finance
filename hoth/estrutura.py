"""Cadastros da planilha Hoth: grupos, plano de contas e bancos."""
from dataclasses import dataclass, field

ENTRADA, SAIDA, MOVIMENTACAO = "Entrada", "Saída", "Movimentação"


@dataclass
class Grupo:
    codigo: str
    nome: str
    natureza: str            # Entrada | Saída | Movimentação (usado nos totais da DFC)
    entra_dre: bool
    entra_dfc: bool
    resultado_apos: str = ""  # linha de resultado acumulado exibida na DRE logo após o grupo
    base_percentual: bool = False  # o subtotal deste grupo é a base dos % da DRE


@dataclass
class Conta:
    codigo: str
    nome: str
    grupo: str               # código do grupo usado na DFC
    grupo_dre: str = ""      # código do grupo na DRE quando diferente do grupo da DFC
    entra_dfc: bool = True
    entra_dre: bool = True
    fixo_variavel: str = ""
    ativa: bool = True
    ordem: int = 0           # ordem na DFC
    ordem_dre: int = 0
    dre_manual: bool = False  # na DRE o valor é digitado na aba "DRE Manual" (competência), não vem dos lançamentos
    observacao: str = ""

    @property
    def grupo_na_dre(self) -> str:
        return self.grupo_dre or self.grupo


@dataclass
class Banco:
    nome: str
    tipo: str                # Conta corrente | Caixa | Aplicação
    saldo_inicial: float = 0.0
    ativo: bool = True


@dataclass
class Estrutura:
    grupos: list[Grupo]
    contas: list[Conta]
    bancos: list[Banco]
    empresa: str = "SUPERMERCADO EXEMPLO LTDA"
    ano: int = 2026
    renomeacoes: dict = field(default_factory=dict)  # nome antigo -> nome novo, para o relatório

    def grupo(self, codigo: str) -> Grupo:
        return next(g for g in self.grupos if g.codigo == codigo)

    def contas_do_grupo(self, codigo: str, *, dre: bool) -> list[Conta]:
        if dre:
            sel = [c for c in self.contas if c.entra_dre and c.grupo_na_dre == codigo]
        else:
            sel = [c for c in self.contas if c.entra_dfc and c.grupo == codigo]
        return sorted(sel, key=lambda c: ((c.ordem_dre or c.ordem) if dre else c.ordem, c.codigo))


GRUPOS_PADRAO = [
    Grupo("01", "FATURAMENTO BRUTO ( = )", ENTRADA, True, True, base_percentual=True),
    Grupo("02", "IMPOSTOS SOB RECEITAS ( - )", SAIDA, True, True, "RECEITA LÍQUIDA ( = )"),
    Grupo("03", "CPV - CUSTO DO PRODUTO VENDIDO ( - )", SAIDA, True, True),
    Grupo("04", "CUSTOS INDIRETOS ( - )", SAIDA, True, True, "MARGEM DE CONTRIBUIÇÃO ( = )"),
    Grupo("05", "DESPESAS COMERCIAIS ( - )", SAIDA, True, True),
    Grupo("06", "DESP. ADMINISTRATIVAS ( - )", SAIDA, True, True),
    Grupo("07", "DESP. C/ PESSOAL ( - )", SAIDA, True, True, "EBITDA - LUCRO OPERACIONAL ( = )"),
    Grupo("08", "RECEITAS NÃO OPERACIONAIS ( + )", ENTRADA, True, True),
    Grupo("09", "DESPESAS NÃO OPERACIONAIS ( - )", SAIDA, True, True, "EBIT - LUCRO LÍQUIDO ( = )"),
    Grupo("10", "BENS E AQUISIÇÕES ( - )", SAIDA, True, True),
    Grupo("11", "DISTRIBUIÇÃO DE LUCROS ( - )", SAIDA, True, False, "RESULTADO LÍQUIDO CAIXA ( = )"),
    Grupo("12", "MOVIMENTAÇÕES BANCÁRIAS", MOVIMENTACAO, False, True),
]

BANCOS_PADRAO = [
    Banco("Santander", "Conta corrente"),
    Banco("Cora", "Conta corrente"),
    Banco("Caixa Loja", "Caixa"),
    Banco("Caixa Econômica 1", "Conta corrente"),
    Banco("Caixa Econômica 2", "Conta corrente"),
    Banco("Santander CDB", "Aplicação"),
    Banco("Santander Contamax", "Aplicação"),
    Banco("Caixa Fundo Renda Fixa", "Aplicação"),
    Banco("Caixa Giro Empresa", "Aplicação"),
]
