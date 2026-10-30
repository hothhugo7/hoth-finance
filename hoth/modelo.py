"""Gera a planilha Hoth (modelo único de fechamento) a partir dos cadastros e lançamentos.

Toda a DFC e a DRE são fórmulas sobre a Tabela `tbLanc` (aba Lançamentos),
filtrando por código da conta + ano + mês. A estrutura das linhas sai do Plano de
Contas e dos Grupos; quando o plano muda, a planilha é gerada de novo por aqui.
"""
import datetime as dt

from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.properties import Outline
from openpyxl.utils import get_column_letter as L
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableFormula, TableStyleInfo

from .estrutura import ENTRADA, MOVIMENTACAO, SAIDA, Estrutura

MESES = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
         "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
MESES_CURTOS = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]

# Identidade visual Hoth: grafite e prata.
GRAFITE, GRAFITE_2, PRATA, CINZA_CLARO, CINZA_TEXTO = "1E1F22", "2B2D31", "C9CDD2", "ECEDEF", "6B6F76"
F_TITULO = Font(name="Calibri", size=16, bold=True, color=GRAFITE)
F_SUB = Font(name="Calibri", size=10, color=CINZA_TEXTO)
F_CAB = Font(name="Calibri", bold=True, color=PRATA)
F_GRUPO = Font(name="Calibri", bold=True, color=GRAFITE)
F_RESULT = Font(name="Calibri", bold=True, color="FFFFFF")
F_AUX = Font(name="Calibri", size=8, color="A0A4AA")
P_CAB = PatternFill("solid", fgColor=GRAFITE)
P_GRUPO = PatternFill("solid", fgColor=CINZA_CLARO)
P_RESULT = PatternFill("solid", fgColor=GRAFITE_2)
P_ALERTA = PatternFill("solid", fgColor="FBE9E7")
BORDA = Border(bottom=Side(style="thin", color="D5D8DC"))
NUM = '#,##0.00;-#,##0.00;"-"'               # tabelas de dados (Lançamentos, cadastros)
NUM_ALERTA = '#,##0.00;[Red]-#,##0.00;"-"'  # linhas de diferença/conferência
PCT = '0.0%;-0.0%;"-"'
DATA = "DD/MM/YYYY"

# Relatórios (DFC, DRE, RESUMO, Faturamento): padrão contábil, negativos entre parênteses.
NUM_REL = '#,##0.00_);(#,##0.00);"–"_)'
NUM_REL_ESCURO = NUM_REL
NUM_REL_RESULTADO = '#,##0.00_);[Red](#,##0.00);"–"_)'   # resultado negativo em vermelho
PCT_REL = '0.0%_);(0.0%);"–"_)'
PCT_REL_ESCURO = PCT_REL
PCT_REL_RESULTADO = '0.0%_);[Red](0.0%);"–"_)'
FONTE = "Segoe UI"
NOITE = "121316"          # faixa de título e capa (mesmo tom do fundo do logo)
R_CAB, R_CAB_2 = "1B1D21", "2A2D33"
R_GRUPO, R_GRUPO_TXT = "DDE1E6", "111317"
R_TOTAL = "0F1012"
R_TEXTO = "2B2E33"
R_LINHA = "E3E6EA"
R_ACUM = "EEF0F3"
F_REL_TITULO = Font(name=FONTE, size=13, bold=True, color="FFFFFF")
F_REL_SUB = Font(name=FONTE, size=9, color="A9AEB6")
F_REL_ANO = Font(name=FONTE, size=11, bold=True, color="E0B04F")
F_REL_CAB = Font(name=FONTE, size=9, bold=True, color="E6E8EB")
F_REL_CAB_2 = Font(name=FONTE, size=8, bold=True, color="A9AEB6")
F_REL_GRUPO = Font(name=FONTE, size=10, bold=True, color=R_GRUPO_TXT)
F_REL_CONTA = Font(name=FONTE, size=9, color=R_TEXTO)
F_REL_CONTA_FORTE = Font(name=FONTE, size=9, bold=True, color="15171A")
F_REL_PREV = Font(name=FONTE, size=9, color="7A7F87")
F_REL_PCT = Font(name=FONTE, size=8, italic=True, color="7A7F87")
F_REL_TOTAL = Font(name=FONTE, size=10, bold=True, color="FFFFFF")
F_REL_AUX = Font(name=FONTE, size=7, color="A0A4AA")
P_REL_CAB = PatternFill("solid", fgColor=R_CAB)
P_REL_CAB_2 = PatternFill("solid", fgColor=R_CAB_2)
P_REL_GRUPO = PatternFill("solid", fgColor=R_GRUPO)
P_REL_TOTAL = PatternFill("solid", fgColor=R_TOTAL)
P_REL_ACUM = PatternFill("solid", fgColor=R_ACUM)
P_NOITE = PatternFill("solid", fgColor=NOITE)
B_CONTA = Border(bottom=Side(style="hair", color="D5D9DE"))
B_GRUPO = Border(top=Side(style="thin", color="9AA1AA"), bottom=Side(style="thin", color="9AA1AA"))
B_TOTAL = Border(top=Side(style="medium", color="C9CDD2"))
LINHAS_TITULO = 3  # faixa escura (1-2) + linha auxiliar oculta (3) com o número do mês

LANC = "tbLanc"
MANUAL_LINHA1, MANUAL_ULTIMA = 6, 400
MANUAL_CODIGOS = f"'DRE Manual'!$A${MANUAL_LINHA1}:$A${MANUAL_ULTIMA}"
MANUAL_VALORES = f"'DRE Manual'!$D${MANUAL_LINHA1}:$O${MANUAL_ULTIMA}"
P_DIGITAR = PatternFill("solid", fgColor="FFF8E1")


def _sim(v: bool) -> str:
    return "Sim" if v else "Não"


def _tabela(ws, nome, cabecalhos, linhas, *, formulas=None, estilo="TableStyleMedium1", larguras=None):
    """Escreve uma Tabela do Excel a partir da linha 1. `formulas` = {coluna: fórmula de coluna calculada}."""
    formulas = formulas or {}
    ws.append(cabecalhos)
    for linha in linhas:
        ws.append([("=" + formulas[c]) if c in formulas else v for c, v in zip(cabecalhos, linha)])
    ultima = max(2, len(linhas) + 1)
    t = Table(displayName=nome, ref=f"A1:{L(len(cabecalhos))}{ultima}")
    t._initialise_columns()
    for col, cab in zip(t.tableColumns, cabecalhos):
        col.name = cab
        if cab in formulas:
            col.calculatedColumnFormula = TableFormula(attr_text=formulas[cab])
    t.tableStyleInfo = TableStyleInfo(name=estilo, showRowStripes=True)
    ws.add_table(t)
    ws.freeze_panes = "A2"
    for i, w in enumerate(larguras or [], start=1):
        ws.column_dimensions[L(i)].width = w
    return t


def _linha_estilo(ws, r, c1, c2, fonte=None, preenchimento=None, formato=None):
    for c in range(c1, c2 + 1):
        cel = ws.cell(r, c)
        if fonte:
            cel.font = fonte
        if preenchimento:
            cel.fill = preenchimento
        if formato:
            cel.number_format = formato


def _titulo(ws, texto, subtitulo):
    ws["A1"] = texto
    ws["A1"].font = F_TITULO
    ws["A2"] = subtitulo
    ws["A2"].font = F_SUB


def _faixa_titulo(ws, titulo, subtitulo, ultima_col):
    """Faixa escura no topo dos relatórios. O logo e o botão Capa entram por cima (acabamento no Excel)."""
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 34
    ws.row_dimensions[2].height = 18
    for r in (1, 2):
        for c in range(1, ultima_col + 3):
            ws.cell(r, c).fill = P_NOITE
    ws["A1"] = titulo
    ws["A1"].font = F_REL_TITULO
    ws["A1"].alignment = Alignment(vertical="center", indent=15)
    ws["A2"] = subtitulo
    ws["A2"].font = F_REL_SUB
    ws["A2"].alignment = Alignment(vertical="top", indent=1)
    ws.row_dimensions[3].hidden = True


def _estilo_relatorio(ws, r, c1, c2, tipo, *, cols_pct=(), cols_prev=(), cols_acum=(), col_codigo=2):
    """Estilo de uma linha de relatório: 'conta', 'grupo', 'total' (faixa escura) ou 'resultado'
    (faixa escura com resultado negativo em vermelho)."""
    resultado = tipo == "resultado"
    escuro = tipo in ("total", "resultado")
    for c in range(c1, c2 + 1):
        cel = ws.cell(r, c)
        if tipo == "grupo":
            cel.fill, cel.border = P_REL_GRUPO, B_GRUPO
        elif escuro:
            cel.fill, cel.border = P_REL_TOTAL, B_TOTAL
        else:
            cel.border = B_CONTA
            if c in cols_acum:
                cel.fill = P_REL_ACUM
        if c == 1:
            cel.font = F_REL_GRUPO if tipo == "grupo" else F_REL_TOTAL if escuro else F_REL_CONTA
            continue
        if c == col_codigo:
            continue
        if c in cols_pct:
            cel.number_format = PCT_REL_RESULTADO if resultado else PCT_REL
            cel.font = F_REL_TOTAL if escuro else (F_REL_GRUPO if tipo == "grupo" else F_REL_PCT)
        else:
            cel.number_format = NUM_REL_RESULTADO if resultado else NUM_REL
            if escuro:
                cel.font = F_REL_TOTAL
            elif tipo == "grupo":
                cel.font = F_REL_GRUPO
            elif c in cols_prev:
                cel.font = F_REL_PREV
            else:
                cel.font = F_REL_CONTA_FORTE if c in cols_acum else F_REL_CONTA
    ws.row_dimensions[r].height = 18 if tipo != "conta" else 16


def _agrupar(ws, linhas, recolhido=True):
    """Linhas de detalhe com botão +/− no grupo (o total fica acima do detalhe)."""
    for r in linhas:
        ws.row_dimensions[r].outlineLevel = 1
        ws.row_dimensions[r].hidden = recolhido
    if linhas and recolhido:
        ws.row_dimensions[linhas[0] - 1].collapsed = True


class GeradorPlanilha:
    def __init__(self, est: Estrutura):
        self.est = est
        self.wb = Workbook()
        self.pos = {}  # posições usadas por RESUMO/Faturamento e pela conferência

    # --------------------------------------------------------------- cadastros
    # -------------------------------------------------------------------- capa
    # Botões e logo são desenhados pelo acabamento no Excel (hoth/acabamento.py) sobre estas áreas.
    BOTOES_CAPA = [
        ("DEMONSTRATIVOS", 21, [("DFC", "Fluxo de caixa", "DFC"), ("DRE", "Resultado do exercício", "DRE"),
                                ("RESUMO", "Grupos e resultados", "RESUMO"),
                                ("FATURAMENTO", "Previsto x realizado", "Faturamento")]),
        ("OPERAÇÃO", 26, [("LANÇAMENTOS", "Todos os bancos", "Lançamentos"),
                          ("DRE MANUAL", "Valores digitados", "DRE Manual"),
                          ("AJUSTES DRE", "Acertos de competência", "Ajustes DRE"),
                          ("ORÇAMENTO", "Valores previstos", "Orçamento")]),
        ("CADASTROS", 31, [("PLANO DE CONTAS", "Contas e grupos", "Plano de Contas"),
                           ("GRUPOS", "Estrutura da DRE e DFC", "Grupos"),
                           ("BANCOS", "Saldo inicial do ano", "Bancos"),
                           ("SALDOS INFORMADOS", "Saldos dos extratos", "Saldos Informados")]),
    ]
    COLUNAS_BOTAO = ["B:D", "E:G", "H:J", "K:M"]

    def _capa(self, meses_fechados: int):
        ws = self.wb["Capa"]
        ws.sheet_view.showGridLines = False
        ws.sheet_view.showRowColHeaders = False
        ws.sheet_view.zoomScale = 100
        ws.column_dimensions["A"].width = 4
        for c in range(2, 14):
            ws.column_dimensions[L(c)].width = 12.5
        ws.column_dimensions["N"].width = 4
        for r in range(1, 56):
            ws.row_dimensions[r].height = 18
            for c in range(1, 30):
                ws.cell(r, c).fill = P_NOITE
        for r in range(2, 10):
            ws.row_dimensions[r].height = 24  # área do logo

        def texto(ref, valor, tamanho=10, cor="C9CDD2", negrito=False, alinh="center", italico=False):
            ws.merge_cells(ref)
            cel = ws[ref.split(":")[0]]
            cel.value = valor
            cel.font = Font(name=FONTE, size=tamanho, color=cor, bold=negrito, italic=italico)
            cel.alignment = Alignment(horizontal=alinh, vertical="center")
            return cel

        texto("B11:M11", f"FECHAMENTO FINANCEIRO  ·  {self.est.ano}", 15, "E6E8EB", True)
        ws.row_dimensions[11].height = 26
        texto("B12:M12", self.est.empresa, 10, "8B9199")
        for c in range(2, 14):
            ws.cell(13, c).border = Border(bottom=Side(style="thin", color="3A3D43"))

        # Indicadores do ano (vêm da DRE)
        texto("B15:M15", "INDICADORES DO EXERCÍCIO", 8, "8B9199", True, "left")
        base = self.pos["dre_base"]
        meses = f'DRE!$D$3:${L(self.pos["dre_col_total"] - 1)}$3'
        reais = f'DRE!$D$5:${L(self.pos["dre_col_total"] - 1)}$5'

        def fechado(linha):
            """Soma o REAL dos meses já fechados (Meses fechados), sem os meses em aberto."""
            faixa = f'DRE!$D${linha}:${L(self.pos["dre_col_total"] - 1)}${linha}'
            return f'=SUMPRODUCT(({meses}<=MesesFechados)*({reais}="REAL")*{faixa})'
        resultados = [k[1] for k in self.pos if isinstance(k, tuple) and k[0] == "dre_resultado"]
        escolhidos = []
        for chave_kpi in ("MARGEM", "EBITDA", "EBIT -"):
            nome = next((n for n in resultados if chave_kpi in n.upper() and n not in escolhidos), None)
            if nome:
                escolhidos.append(nome)
        kpis = [("FATURAMENTO BRUTO", base)] + [
            (n.split("(")[0].strip().replace(" - ", "  ·  "), self.pos[("dre_resultado", n)]) for n in escolhidos]
        fundo_kpi = PatternFill("solid", fgColor="1C1E22")
        borda_kpi = Side(style="thin", color="2E3137")
        for (rotulo, linha), cols in zip(kpis[:4], self.COLUNAS_BOTAO):
            c1, c2 = cols.split(":")
            for r in (16, 17, 18):
                for c in range(ws[f"{c1}1"].column, ws[f"{c2}1"].column + 1):
                    cel = ws.cell(r, c)
                    cel.fill = fundo_kpi
                    cel.border = Border(top=borda_kpi if r == 16 else None, bottom=borda_kpi if r == 18 else None,
                                        left=borda_kpi if c == ws[f"{c1}1"].column else None,
                                        right=borda_kpi if c == ws[f"{c2}1"].column else None)
            texto(f"{c1}16:{c2}16", rotulo, 8, "8B9199", True)
            v = texto(f"{c1}17:{c2}17", fechado(linha), 17, "FFFFFF", True)
            v.number_format = '"R$ "#,##0;[Red]"R$ "(#,##0);"–"'
            p = texto(f"{c1}18:{c2}18", f"=IFERROR({fechado(linha)[1:]}/{fechado(base)[1:]},0)", 9, "C9A227")
            p.number_format = '0.0% "do faturamento";(0.0%) "do faturamento";"–"'
            if linha == base:
                p.value = '="acumulado em "&MesesFechados&" meses"'
                p.number_format = "@"
        ws.row_dimensions[17].height = 30

        # Rótulos das seções de botões
        for secao, linha, _ in self.BOTOES_CAPA:
            texto(f"B{linha - 1}:M{linha - 1}", secao, 8, "8B9199", True, "left")
            for r in range(linha, linha + 3):
                ws.row_dimensions[r].height = 20

        # Parâmetros (células editáveis usadas pelas fórmulas)
        texto("B35:M35", "PARÂMETROS", 8, "8B9199", True, "left")
        entrada = PatternFill("solid", fgColor="24262B")
        parametros = [("Empresa", self.est.empresa), ("Ano base", self.est.ano), ("Meses fechados", meses_fechados),
                      ("Planilha gerada em", dt.datetime.now().strftime("%d/%m/%Y %H:%M"))]
        for i, (rotulo, valor) in enumerate(parametros):
            r = 36 + i
            texto(f"B{r}:C{r}", rotulo, 9, "A9AEB6", False, "left")
            cel = texto(f"D{r}:G{r}", valor, 10, "E0B04F" if rotulo in ("Ano base", "Meses fechados") else "E6E8EB",
                        True, "left")
            if rotulo in ("Ano base", "Meses fechados"):
                for c in range(4, 8):
                    ws.cell(r, c).fill = entrada
        self.wb.defined_names["AnoBase"] = DefinedName("AnoBase", attr_text="Capa!$D$37")
        self.wb.defined_names["MesesFechados"] = DefinedName("MesesFechados", attr_text="Capa!$D$38")
        texto("I36:M36", "Ano base e meses fechados podem ser alterados (células com número dourado).", 8,
              "6B7078", alinh="left", italico=True)

        texto("B41:M41", "COMO USAR", 8, "8B9199", True, "left")
        regras = [
            "Extratos do Santander e da Cora: importe pelo app Hoth (classifica, guarda versão anterior e grava aqui).",
            "Caixa Loja: digite em Lançamentos com Banco = Caixa Loja e escolha a Conta na lista.",
            "Faturamento bruto (Curva ABC), CPV, copa e cozinha, taxas das maquininhas e pró-labore: aba DRE Manual.",
            "DFC e DRE: clique no + à esquerda para abrir um grupo, ou nos botões 1 e 2 do topo para abrir ou fechar todos.",
            "Contas e grupos novos: cadastre pelo app Hoth, que recria as linhas da DFC e da DRE.",
        ]
        for i, t in enumerate(regras):
            texto(f"B{42 + i}:M{42 + i}", "▸  " + t, 9, "A9AEB6", alinh="left")
        for c in range(2, 14):
            ws.cell(48, c).border = Border(bottom=Side(style="thin", color="3A3D43"))
        texto("B49:M49", "HOTH SOLUTIONS  ·  SOLUÇÕES FINANCEIRAS", 8, "6B7078", True)
        ws.sheet_view.selection[0].activeCell = "A1"
        ws.sheet_view.selection[0].sqref = "A1"

    def _cadastros(self, ajustes, orcamento, saldos, auditoria):
        est, wb = self.est, self.wb
        nome_grupo = {g.codigo: g.nome for g in est.grupos}

        ws = wb.create_sheet("Plano de Contas")
        _tabela(ws, "tbPlano",
                ["Código", "Conta", "Grupo", "Grupo DRE", "Entra DFC", "Entra DRE", "Valor na DRE", "Fixo/Variável", "Ativa",
                 "Observação", "Ordem DFC", "Ordem DRE"],
                [[c.codigo, c.nome, nome_grupo[c.grupo], nome_grupo.get(c.grupo_dre, ""), _sim(c.entra_dfc),
                  _sim(c.entra_dre), ("Manual" if c.dre_manual else "Lançamentos") if c.entra_dre else "",
                  c.fixo_variavel, _sim(c.ativa), c.observacao, c.ordem, c.ordem_dre]
                 for c in sorted(est.contas, key=lambda c: c.codigo)],
                larguras=[9, 50, 38, 30, 10, 10, 13, 13, 8, 50, 10, 10])

        ws = wb.create_sheet("Grupos")
        _tabela(ws, "tbGrupos",
                ["Código", "Grupo", "Natureza", "Entra DRE", "Entra DFC", "Resultado após o grupo", "Base %"],
                [[g.codigo, g.nome, g.natureza, _sim(g.entra_dre), _sim(g.entra_dfc), g.resultado_apos,
                  _sim(g.base_percentual)] for g in est.grupos],
                larguras=[9, 42, 14, 10, 10, 34, 8])

        ws = wb.create_sheet("Bancos")
        _tabela(ws, "tbBancos", ["Banco", "Tipo", "Saldo inicial", "Ativo"],
                [[b.nome, b.tipo, b.saldo_inicial, _sim(b.ativo)] for b in est.bancos], larguras=[26, 16, 16, 8])
        for r in range(2, len(est.bancos) + 2):
            ws.cell(r, 3).number_format = NUM

        ws = wb.create_sheet("Saldos Informados")
        _tabela(ws, "tbSaldos", ["Banco", "Ano", "Mês", "Saldo inicial informado"],
                [[s["banco"], s["ano"], s["mes"], s["saldo"]] for s in saldos], larguras=[26, 8, 6, 22])
        for r in range(2, len(saldos) + 2):
            ws.cell(r, 4).number_format = NUM

        cod = 'IF(tb{t}[[#This Row],[Conta]]="","",IFERROR(INDEX(tbPlano[Código],MATCH(tb{t}[[#This Row],[Conta]],tbPlano[Conta],0)),"CONTA?"))'
        ws = wb.create_sheet("Ajustes DRE")
        _tabela(ws, "tbAjustes", ["Ano", "Mês", "Conta", "Código", "Tipo", "Valor", "Motivo"],
                [[a["ano"], a["mes"], a["conta"], None, a["tipo"], a["valor"], a["motivo"]] for a in ajustes],
                formulas={"Código": cod.format(t="Ajustes")}, larguras=[8, 6, 44, 9, 11, 15, 80])
        for r in range(2, len(ajustes) + 2):
            ws.cell(r, 6).number_format = NUM
        dv = DataValidation(type="list", formula1='"SUBSTITUI,SOMA"', allow_blank=False)
        ws.add_data_validation(dv)
        dv.add("E2:E5000")
        self._validar_conta(ws, "C2:C5000")

        ws = wb.create_sheet("Orçamento")
        _tabela(ws, "tbOrc", ["Ano", "Mês", "Conta", "Código", "Valor"],
                [[o["ano"], o["mes"], o["conta"], None, o["valor"]] for o in orcamento],
                formulas={"Código": cod.format(t="Orc")}, larguras=[8, 6, 44, 9, 15])
        for r in range(2, len(orcamento) + 2):
            ws.cell(r, 5).number_format = NUM
        self._validar_conta(ws, "C2:C5000")

        ws = wb.create_sheet("Auditoria")
        _tabela(ws, "tbAuditoria", ["Data/hora", "Ação", "Detalhe", "Linhas", "Arquivo", "Backup"],
                auditoria, larguras=[18, 22, 70, 9, 50, 50])
        for r in range(2, len(auditoria) + 2):
            ws.cell(r, 1).number_format = "DD/MM/YYYY HH:MM"

        wb.defined_names["lstContas"] = DefinedName("lstContas", attr_text="tbPlano[Conta]")
        wb.defined_names["lstBancos"] = DefinedName("lstBancos", attr_text="tbBancos[Banco]")
        wb.defined_names["lstGrupos"] = DefinedName("lstGrupos", attr_text="tbGrupos[Grupo]")
        ws = wb["Plano de Contas"]
        for col in ("C", "D"):
            dv = DataValidation(type="list", formula1="=lstGrupos", allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(f"{col}2:{col}1000")

    def _validar_conta(self, ws, faixa):
        dv = DataValidation(type="list", formula1="=lstContas", allow_blank=True, showErrorMessage=True,
                            errorTitle="Conta inválida", error="Escolha uma conta do Plano de Contas.")
        ws.add_data_validation(dv)
        dv.add(faixa)

    # ------------------------------------------------------------- lançamentos
    def _lancamentos(self, lancamentos):
        ws = self.wb.create_sheet("Lançamentos", 1)
        cab = ["ID", "Banco", "Data", "Ano", "Mês", "Descrição", "Documento", "Valor", "Conta", "Código", "Grupo",
               "Origem", "Referência", "Observação", "Importado em"]
        this = lambda c: f"{LANC}[[#This Row],[{c}]]"
        formulas = {
            "Ano": f'IF({this("Data")}="","",YEAR({this("Data")}))',
            "Mês": f'IF({this("Data")}="","",MONTH({this("Data")}))',
            "Código": (f'IF({this("Conta")}="","",IFERROR(INDEX(tbPlano[Código],'
                       f'MATCH({this("Conta")},tbPlano[Conta],0)),"CONTA?"))'),
            "Grupo": (f'IF({this("Conta")}="","",IFERROR(INDEX(tbPlano[Grupo],'
                      f'MATCH({this("Conta")},tbPlano[Conta],0)),""))'),
        }
        linhas = [[l["id"], l["banco"], l["data"], None, None, l["descricao"], l["documento"], l["valor"],
                   l["conta"], None, None, l["origem"], l["referencia"], l["observacao"], l.get("importado_em")]
                  for l in lancamentos]
        _tabela(ws, LANC, cab, linhas, formulas=formulas,
                larguras=[18, 18, 11, 6, 5, 58, 12, 14, 44, 8, 34, 24, 18, 40, 16])
        n = len(linhas) + 1
        for r in range(2, n + 1):
            ws.cell(r, 3).number_format = DATA
            ws.cell(r, 8).number_format = NUM
            ws.cell(r, 15).number_format = "DD/MM/YYYY HH:MM"
        dv = DataValidation(type="list", formula1="=lstBancos", allow_blank=False)
        ws.add_data_validation(dv)
        dv.add(f"B2:B{n + 20000}")
        self._validar_conta(ws, f"I2:I{n + 20000}")
        ws.auto_filter.ref = None

    # --------------------------------------------------------------------- DFC
    def _dfc(self):
        est = self.est
        ws = self.wb.create_sheet("DFC")
        _faixa_titulo(ws, "DFC  ·  FLUXO DE CAIXA",
                      "Regime de caixa. Entradas (+), saídas entre parênteses. Clique no + à esquerda para abrir um grupo.",
                      15)
        ws["N2"] = '="Exercício "&AnoBase'
        ws["N2"].font = F_REL_ANO
        ws["N2"].alignment = Alignment(horizontal="right")
        ws.sheet_properties.outlinePr = Outline(summaryBelow=False, summaryRight=True)
        ws.column_dimensions["A"].width = 56
        ws.column_dimensions["B"].width = 18
        for m in range(1, 13):
            ws.cell(3, 2 + m, m)
            ws.column_dimensions[L(2 + m)].width = 14
        ws.column_dimensions["O"].width = 17
        cab = ["FLUXO DE CAIXA", "Código"] + MESES + ["ACUMULADO"]
        for c, v in enumerate(cab, start=1):
            cel = ws.cell(4, c, v)
            cel.font, cel.fill = F_REL_CAB, P_REL_CAB
            cel.alignment = Alignment(horizontal="left" if c == 1 else "center", vertical="center")
            cel.border = Border(bottom=Side(style="medium", color="C9CDD2"))
        ws.row_dimensions[4].height = 24
        ws.freeze_panes = "C5"
        mc = lambda c: f"{L(c)}$3"
        soma_lanc = lambda r, c: (f"=SUMIFS({LANC}[Valor],{LANC}[Código],$B{r},{LANC}[Ano],AnoBase,"
                                  f"{LANC}[Mês],{mc(c)})")
        acum = {15}
        r = 5
        bancos = [b for b in est.bancos if b.ativo]
        # SALDO INICIAL (linhas preenchidas depois que o bloco de bancos tiver posição)
        r_saldo_ini = r
        ws.cell(r, 1, "SALDO INICIAL")
        linhas_saldo_banco = {}
        for i, b in enumerate(bancos, start=1):
            linhas_saldo_banco[b.nome] = r + i
            ws.cell(r + i, 1, f"   {b.nome}")
            ws.cell(r + i, 2, b.nome).font = F_REL_AUX
        r += len(bancos) + 2

        def bloco_grupos(naturezas, titulo):
            nonlocal r
            r_total = r
            ws.cell(r, 1, titulo)
            r += 1
            cabecalhos = []
            for g in est.grupos:
                if not g.entra_dfc or g.natureza not in naturezas:
                    continue
                contas = est.contas_do_grupo(g.codigo, dre=False)
                r_g = r
                cabecalhos.append(r_g)
                ws.cell(r, 1, g.nome)
                ws.cell(r, 2, g.codigo).font = F_REL_AUX
                r += 1
                for conta in contas:
                    ws.cell(r, 1, f"   {conta.nome}")
                    ws.cell(r, 2, conta.codigo).font = F_REL_AUX
                    for c in range(3, 15):
                        ws.cell(r, c, soma_lanc(r, c))
                    ws.cell(r, 15, f"=SUM(C{r}:N{r})")
                    _estilo_relatorio(ws, r, 1, 15, "conta", cols_acum=acum)
                    r += 1
                for c in range(3, 16):
                    ws.cell(r_g, c, f"=SUM({L(c)}{r_g + 1}:{L(c)}{r - 1})" if contas else 0)
                _estilo_relatorio(ws, r_g, 1, 15, "grupo")
                _agrupar(ws, range(r_g + 1, r))
                self.pos[("dfc_grupo", g.codigo)] = r_g
            for c in range(3, 16):
                ws.cell(r_total, c, "=" + "+".join(f"{L(c)}{x}" for x in cabecalhos) if cabecalhos else 0)
            _estilo_relatorio(ws, r_total, 1, 15, "total")
            r += 1
            return r_total

        r_ent = bloco_grupos({ENTRADA}, "TOTAL DE ENTRADAS ( + )")
        r_sai = bloco_grupos({SAIDA}, "TOTAL DE SAÍDAS ( − )")
        r_mov = bloco_grupos({MOVIMENTACAO}, "MOVIMENTAÇÕES ( +/− )")
        self.pos["dfc_entradas"], self.pos["dfc_saidas"], self.pos["dfc_movimentacoes"] = r_ent, r_sai, r_mov

        r_sem = r
        ws.cell(r, 1, "SEM CLASSIFICAÇÃO")
        ws.cell(r, 2, "").font = F_REL_AUX
        ws.cell(r + 1, 1, "CONTA INVÁLIDA (não existe no Plano de Contas)")
        ws.cell(r + 1, 2, "CONTA?").font = F_REL_AUX
        for c in range(3, 15):
            ws.cell(r, c, f'=SUMIFS({LANC}[Valor],{LANC}[Código],"",{LANC}[Ano],AnoBase,{LANC}[Mês],{mc(c)})')
            ws.cell(r + 1, c, soma_lanc(r + 1, c))
        for rr in (r, r + 1):
            ws.cell(rr, 15, f"=SUM(C{rr}:N{rr})")
            _estilo_relatorio(ws, rr, 1, 15, "conta")
            _linha_estilo(ws, rr, 1, 15, preenchimento=P_ALERTA)
        r += 3

        r_movmes = r
        ws.cell(r, 1, "MOVIMENTO DO MÊS ( +/− )")
        ws.cell(r + 1, 1, "Conferência: soma de todos os lançamentos do mês")
        ws.cell(r + 2, 1, "Diferença (deve ser zero; senão há conta sem linha na DFC)")
        ws.cell(r + 3, 1, "SALDO FINAL")
        for c in range(3, 16):
            col = L(c)
            ws.cell(r, c, f"={col}{r_ent}+{col}{r_sai}+{col}{r_mov}+{col}{r_sem}+{col}{r_sem + 1}")
            if c < 15:
                ws.cell(r + 1, c, f"=SUMIFS({LANC}[Valor],{LANC}[Ano],AnoBase,{LANC}[Mês],{mc(c)})")
                ws.cell(r + 3, c, f"={col}{r_saldo_ini}+{col}{r}")
            else:
                ws.cell(r + 1, c, f"=SUM(C{r + 1}:N{r + 1})")
                ws.cell(r + 3, c, f"=N{r + 3}")
            ws.cell(r + 2, c, f"=ROUND({col}{r}-{col}{r + 1},2)")
        _estilo_relatorio(ws, r, 1, 15, "resultado")
        for rr in (r + 1, r + 2):
            _estilo_relatorio(ws, rr, 1, 15, "conta")
            _linha_estilo(ws, rr, 1, 15, F_REL_PREV)
        _estilo_relatorio(ws, r + 3, 1, 15, "resultado")
        self.pos["dfc_movimento"], self.pos["dfc_saldo_final"] = r_movmes, r + 3
        r += 6

        ws.cell(r, 1, "SALDO POR BANCO")
        for c in range(1, 16):
            cel = ws.cell(r, c)
            cel.font, cel.fill = F_REL_CAB, P_REL_CAB
        ws.row_dimensions[r].height = 22
        r += 1
        for b in bancos:
            ri, rm, rf, rinf, rdif = r + 1, r + 2, r + 3, r + 4, r + 5
            ws.cell(r, 1, b.nome)
            rotulos = ["   Saldo inicial", "   Movimento do mês", "   Saldo final",
                       "   Saldo inicial informado (extrato)", "   Diferença (calculado − informado)"]
            for k, rot in enumerate(rotulos):
                ws.cell(ri + k, 1, rot)
                ws.cell(ri + k, 2, b.nome).font = F_REL_AUX
            for c in range(3, 15):
                col, ant = L(c), L(c - 1)
                ws.cell(ri, c, f"=IFERROR(INDEX(tbBancos[Saldo inicial],MATCH($B{ri},tbBancos[Banco],0)),0)"
                        if c == 3 else f"={ant}{rf}")
                ws.cell(rm, c, f"=SUMIFS({LANC}[Valor],{LANC}[Banco],$B{rm},{LANC}[Ano],AnoBase,{LANC}[Mês],{mc(c)})")
                ws.cell(rf, c, f"={col}{ri}+{col}{rm}")
                crit = f"tbSaldos[Banco],$B{rinf},tbSaldos[Ano],AnoBase,tbSaldos[Mês],{mc(c)}"
                ws.cell(rinf, c, f'=IF(COUNTIFS({crit})=0,"",SUMIFS(tbSaldos[Saldo inicial informado],{crit}))')
                ws.cell(rdif, c, f'=IF({col}{rinf}="","",ROUND({col}{ri}-{col}{rinf},2))')
            ws.cell(rm, 15, f"=SUM(C{rm}:N{rm})")
            ws.cell(ri, 15, f"=C{ri}")
            ws.cell(rf, 15, f"=N{rf}")
            # a linha do banco mostra o saldo final; o detalhe abre no +
            for c in range(3, 16):
                ws.cell(r, c, f"={L(c)}{rf}")
            _estilo_relatorio(ws, r, 1, 15, "grupo")
            for rr in (ri, rm, rf, rinf, rdif):
                _estilo_relatorio(ws, rr, 1, 15, "conta", cols_acum=acum)
            _linha_estilo(ws, rf, 3, 15, F_REL_CONTA_FORTE)
            _agrupar(ws, range(ri, rdif + 1))
            # SALDO INICIAL no topo aponta para o bloco do banco
            for c in range(3, 16):
                ws.cell(linhas_saldo_banco[b.nome], c, f"={L(c)}{ri}")
            _estilo_relatorio(ws, linhas_saldo_banco[b.nome], 1, 15, "conta", cols_acum=acum)
            self.pos[("dfc_banco", b.nome)] = ri
            r += 7
        topo = list(linhas_saldo_banco.values())
        for c in range(3, 16):
            ws.cell(r_saldo_ini, c, f"=SUM({L(c)}{topo[0]}:{L(c)}{topo[-1]})")
        _estilo_relatorio(ws, r_saldo_ini, 1, 15, "resultado")
        _agrupar(ws, topo)

    # --------------------------------------------------------------------- DRE
    def _dre(self):
        est = self.est
        ws = self.wb.create_sheet("DRE")
        col_mes = {m: 4 + 4 * (m - 1) for m in range(1, 13)}  # coluna PREV do mês
        c_tot = 4 + 48
        ultima_col = c_tot + 4
        _faixa_titulo(ws, "DRE  ·  RESULTADO DO EXERCÍCIO",
                      "Regime de competência. PREV = orçamento; REAL = lançamentos, DRE Manual e ajustes. "
                      "% sobre o faturamento bruto. Clique no + à esquerda para abrir um grupo.", ultima_col)
        ws["L2"] = '="Exercício "&AnoBase'
        ws["L2"].font = F_REL_ANO
        ws.sheet_properties.outlinePr = Outline(summaryBelow=False, summaryRight=True)
        ws.column_dimensions["A"].width = 64
        ws.column_dimensions["B"].width = 8
        ws.column_dimensions["C"].width = 10
        separador = Side(style="thin", color="B9BFC7")
        for m, c in col_mes.items():
            ws.merge_cells(start_row=4, start_column=c, end_row=4, end_column=c + 3)
            ws.cell(4, c, MESES[m - 1])
            for k, sub in enumerate(["PREV", "REAL", "PREV %", "REAL %"]):
                ws.cell(3, c + k, m)
                ws.cell(5, c + k, sub)
                ws.column_dimensions[L(c + k)].width = 13 if k < 2 else 8
        ws.merge_cells(start_row=4, start_column=c_tot, end_row=4, end_column=c_tot + 3)
        ws.cell(4, c_tot, "TOTAL DO EXERCÍCIO")
        for k, sub in enumerate(["PREV", "REAL", "PREV %", "REAL %"]):
            ws.cell(5, c_tot + k, sub)
            ws.column_dimensions[L(c_tot + k)].width = 15 if k < 2 else 8
        ws.cell(4, c_tot + 4, "MÉDIA")
        ws.cell(5, c_tot + 4, "REAL")
        ws.column_dimensions[L(c_tot + 4)].width = 15
        ws.cell(4, 1, "DEMONSTRATIVO")
        ws.cell(5, 1, "Conta")
        ws.cell(5, 2, "Código")
        ws.cell(5, 3, "Fixo/Var.")
        for c in range(1, ultima_col + 1):
            for rr, fonte, fundo in ((4, F_REL_CAB, P_REL_CAB), (5, F_REL_CAB_2, P_REL_CAB_2)):
                cel = ws.cell(rr, c)
                cel.font, cel.fill = fonte, fundo
                cel.alignment = Alignment(horizontal="left" if c == 1 else "center", vertical="center")
            ws.cell(5, c).border = Border(bottom=Side(style="medium", color="C9CDD2"))
        ws.row_dimensions[4].height = 22
        ws.row_dimensions[5].height = 18
        ws.freeze_panes = "D6"

        crit = lambda r, c, tb: f"{tb}[Código],$B{r},{tb}[Ano],AnoBase,{tb}[Mês],{L(c)}$3"

        def real(r, c, conta, mes):
            soma = f'{crit(r, c, "tbAjustes")},tbAjustes[Tipo],"SOMA"'
            if conta.dre_manual:
                return (f"=IFERROR(INDEX({MANUAL_VALORES},MATCH($B{r},{MANUAL_CODIGOS},0),{mes}),0)"
                        f"+SUMIFS(tbAjustes[Valor],{soma})")
            subst = f'{crit(r, c, "tbAjustes")},tbAjustes[Tipo],"SUBSTITUI"'
            return (f"=IF(COUNTIFS({subst})>0,SUMIFS(tbAjustes[Valor],{subst}),"
                    f"SUMIFS({LANC}[Valor],{crit(r, c, LANC)}))+SUMIFS(tbAjustes[Valor],{soma})")

        r = 6
        base = None
        cabecalhos_grupo = []
        linhas_resultado = []
        linhas_conta = []

        def totais_linha(r):
            prevs = "+".join(f"{L(col_mes[m])}{r}" for m in range(1, 13))
            reais = "+".join(f"{L(col_mes[m] + 1)}{r}" for m in range(1, 13))
            ws.cell(r, c_tot, f"={prevs}")
            ws.cell(r, c_tot + 1, f"={reais}")
            ws.cell(r, c_tot + 4, f"=IFERROR({L(c_tot + 1)}{r}/MesesFechados,0)")

        def percentuais(r):
            for c in list(col_mes.values()) + [c_tot]:
                ws.cell(r, c + 2, f"=IFERROR({L(c)}{r}/{L(c)}${base},0)")
                ws.cell(r, c + 3, f"=IFERROR({L(c + 1)}{r}/{L(c + 1)}${base},0)")

        for g in est.grupos:
            if not g.entra_dre:
                continue
            contas = est.contas_do_grupo(g.codigo, dre=True)
            r_g = r
            if g.base_percentual and base is None:
                base = r_g
            cabecalhos_grupo.append(r_g)
            ws.cell(r, 1, g.nome)
            ws.cell(r, 2, g.codigo).font = F_REL_AUX
            r += 1
            for conta in contas:
                ws.cell(r, 1, f"   {conta.nome}")
                ws.cell(r, 2, conta.codigo).font = F_REL_AUX
                ws.cell(r, 3, conta.fixo_variavel).font = F_REL_AUX
                for m, c in col_mes.items():
                    ws.cell(r, c, f"=SUMIFS(tbOrc[Valor],{crit(r, c, 'tbOrc')})")
                    ws.cell(r, c + 1, real(r, c + 1, conta, m))
                totais_linha(r)
                linhas_conta.append(r)
                r += 1
            for m, c in list(col_mes.items()) + [(0, c_tot)]:
                for k in (0, 1):
                    cc = c + k
                    ws.cell(r_g, cc, f"=SUM({L(cc)}{r_g + 1}:{L(cc)}{r - 1})" if contas else 0)
            ws.cell(r_g, c_tot + 4, f"=IFERROR({L(c_tot + 1)}{r_g}/MesesFechados,0)")
            _agrupar(ws, range(r_g + 1, r))
            self.pos[("dre_grupo", g.codigo)] = r_g
            if g.resultado_apos:
                ws.cell(r, 1, g.resultado_apos)
                ws.cell(r, 2, "RES").font = Font(name=FONTE, size=7, color="5B6068")
                for m, c in list(col_mes.items()) + [(0, c_tot)]:
                    for k in (0, 1):
                        ws.cell(r, c + k, "=" + "+".join(f"{L(c + k)}{x}" for x in cabecalhos_grupo))
                ws.cell(r, c_tot + 4, f"=IFERROR({L(c_tot + 1)}{r}/MesesFechados,0)")
                linhas_resultado.append(r)
                self.pos[("dre_resultado", g.resultado_apos)] = r
                r += 1
            r += 1
        self.pos["dre_base"] = base
        # Estilo e percentuais depois que a linha base é conhecida
        cols_pct = {c + k for c in list(col_mes.values()) + [c_tot] for k in (2, 3)}
        cols_prev = set(col_mes.values()) | {c_tot}
        cols_acum = set(range(c_tot, c_tot + 5))
        for rr in range(6, r):
            if ws.cell(rr, 1).value is None:
                ws.row_dimensions[rr].height = 8
                continue
            percentuais(rr)
            tipo = "grupo" if rr in cabecalhos_grupo else "resultado" if rr in linhas_resultado else "conta"
            _estilo_relatorio(ws, rr, 1, ultima_col, tipo, cols_pct=cols_pct, cols_prev=cols_prev,
                              cols_acum=cols_acum)
            if tipo == "conta":
                ws.cell(rr, 3).font = F_REL_AUX
            for c in col_mes.values():  # separa os meses
                cel = ws.cell(rr, c)
                cel.border = Border(left=separador, top=cel.border.top, bottom=cel.border.bottom)
        self.pos["dre_col_mes"] = col_mes
        self.pos["dre_col_total"] = c_tot

    def _dre_manual(self, valores):
        """Grade conta x mês para os valores da DRE que são digitados (competência), ex.: pró-labore."""
        est = self.est
        ws = self.wb.create_sheet("DRE Manual")
        ws.sheet_view.showGridLines = False
        _titulo(ws, "DRE MANUAL - VALORES DIGITADOS", "Digite nas células amarelas. Despesa com sinal negativo. "
                "Estes valores vão direto para a DRE (não passam pela DFC). Ano:")
        ws["H2"] = "=AnoBase"
        ws["H2"].font = F_GRUPO
        cab = ["Código", "Conta", "Grupo", *MESES_CURTOS, "TOTAL"]
        for c, v in enumerate(cab, start=1):
            ws.cell(MANUAL_LINHA1 - 1, c, v)
        _linha_estilo(ws, MANUAL_LINHA1 - 1, 1, len(cab), F_CAB, P_CAB)
        for c, w in zip("ABC", (9, 46, 34)):
            ws.column_dimensions[c].width = w
        for c in range(4, 17):
            ws.column_dimensions[L(c)].width = 13
        ws.freeze_panes = f"D{MANUAL_LINHA1}"
        por_conta = {}
        for v in valores:
            if v["ano"] == est.ano:
                k = (v["conta"], v["mes"])
                por_conta[k] = por_conta.get(k, 0.0) + v["valor"]  # soma: duas contas mescladas
        r = MANUAL_LINHA1
        for g in est.grupos:
            for conta in est.contas_do_grupo(g.codigo, dre=True):
                if not conta.dre_manual:
                    continue
                ws.cell(r, 1, conta.codigo).font = F_AUX
                ws.cell(r, 2, conta.nome)
                ws.cell(r, 3, g.nome).font = F_SUB
                for m in range(1, 13):
                    cel = ws.cell(r, 3 + m, por_conta.get((conta.nome, m)))
                    cel.fill, cel.number_format = P_DIGITAR, NUM
                ws.cell(r, 16, f"=SUM(D{r}:O{r})").number_format = NUM
                r += 1
        assert r <= MANUAL_ULTIMA, "aumente MANUAL_ULTIMA"

    # ---------------------------------------------------------- RESUMO e Fat.
    def _resumo(self):
        est = self.est
        ws = self.wb.create_sheet("RESUMO")
        ws.sheet_view.showGridLines = False
        col_mes, c_tot = self.pos["dre_col_mes"], self.pos["dre_col_total"]
        cols = [(MESES[m - 1], col_mes[m]) for m in range(1, 13)] + [("TOTAL DO ANO", c_tot)]
        _faixa_titulo(ws, "RESUMO DA DRE", "Grupos e resultados, previsto x realizado. % sobre o faturamento.",
                      1 + 3 * len(cols))
        ws.row_dimensions[3].hidden = False
        ws.column_dimensions["A"].width = 44
        for i, (nome, _) in enumerate(cols):
            c = 2 + 3 * i
            ws.merge_cells(start_row=4, start_column=c, end_row=4, end_column=c + 2)
            ws.cell(4, c, nome)
            for k, sub in enumerate(["PREV", "REAL", "REAL %"]):
                ws.cell(5, c + k, sub)
                ws.column_dimensions[L(c + k)].width = 13 if k < 2 else 8
        ultima = 1 + 3 * len(cols)
        for rr in (4, 5):
            _linha_estilo(ws, rr, 1, ultima, F_CAB, P_CAB)
            for c in range(1, ultima + 1):
                ws.cell(rr, c).alignment = Alignment(horizontal="center")
        ws.cell(5, 1, "Linha da DRE")
        ws.freeze_panes = "B6"
        r = 6
        for g in est.grupos:
            if not g.entra_dre:
                continue
            itens = [(g.nome, self.pos[("dre_grupo", g.codigo)], False)]
            if g.resultado_apos:
                itens.append((g.resultado_apos, self.pos[("dre_resultado", g.resultado_apos)], True))
            for nome, linha_dre, resultado in itens:
                ws.cell(r, 1, nome)
                for i, (_, cd) in enumerate(cols):
                    c = 2 + 3 * i
                    ws.cell(r, c, f"=DRE!{L(cd)}{linha_dre}").number_format = NUM
                    ws.cell(r, c + 1, f"=DRE!{L(cd + 1)}{linha_dre}").number_format = NUM
                    ws.cell(r, c + 2, f"=DRE!{L(cd + 3)}{linha_dre}").number_format = PCT
                if resultado:
                    _linha_estilo(ws, r, 1, ultima, F_RESULT, P_RESULT)
                r += 1

    def _faturamento(self):
        ws = self.wb.create_sheet("Faturamento")
        _faixa_titulo(ws, "FATURAMENTO E RECEBIMENTO",
                      "Faturamento (competência) vem da DRE; recebimento realizado (caixa) vem da DFC.", 15)
        ws.column_dimensions["A"].width = 52
        for c in range(2, 16):
            ws.column_dimensions[L(c)].width = 13
        cab = ["", *MESES_CURTOS, "TOTAL", "MÉDIA"]
        base, col_mes = self.pos["dre_base"], self.pos["dre_col_mes"]
        r_rec = self.pos[("dfc_grupo", "01")]
        for topo, titulo in ((4, "FATURAMENTO"), (10, "RECEBIMENTO")):
            for c, v in enumerate(cab, start=1):
                cel = ws.cell(topo, c, titulo if c == 1 else v)
                cel.font, cel.fill = F_REL_CAB, P_REL_CAB
                cel.alignment = Alignment(horizontal="left" if c == 1 else "center", vertical="center")
                cel.border = Border(bottom=Side(style="medium", color="C9CDD2"))
            ws.row_dimensions[topo].height = 22
        rot = ["Previsto", "Realizado", "Variação R$", "Variação %"]
        for k, t in enumerate(rot):
            ws.cell(5 + k, 1, t)
            ws.cell(11 + k, 1, t)
        for m in range(1, 13):
            c, cd = 1 + m, col_mes[m]
            col = L(c)
            ws.cell(5, c, f"=DRE!{L(cd)}{base}")
            ws.cell(6, c, f"=DRE!{L(cd + 1)}{base}")
            ws.cell(12, c, f"=DFC!{L(2 + m)}{r_rec}")
            for top in (5, 11):
                ws.cell(top + 2, c, f"={col}{top + 1}-{col}{top}")
                ws.cell(top + 3, c, f"=IFERROR({col}{top + 1}/{col}{top}-1,0)")
        for top in (5, 11):
            for k in range(3):
                rr = top + k
                ws.cell(rr, 14, f"=SUM(B{rr}:M{rr})")
                ws.cell(rr, 15, f"=IFERROR(N{rr}/MesesFechados,0)")
            ws.cell(top + 3, 14, f"=IFERROR(N{top + 1}/N{top}-1,0)")
            for rr in range(top, top + 4):
                _estilo_relatorio(ws, rr, 1, 15, "conta", cols_pct=set(range(2, 16)) if rr == top + 3 else (),
                                  cols_prev=set(range(2, 16)) if rr == top else (), cols_acum={14, 15},
                                  col_codigo=None)
            _linha_estilo(ws, top + 1, 1, 13, F_REL_CONTA_FORTE)
        for c in range(2, 14):
            ws.cell(11, c).fill = P_DIGITAR  # recebimento previsto: digitado

        # Série do realizado só até o último mês fechado (meses em aberto ficam fora do gráfico).
        ws.cell(17, 1, "Gráfico: previsto")
        ws.cell(18, 1, "Gráfico: realizado")
        for m in range(1, 13):
            col = L(1 + m)
            ws.cell(16, 1 + m, MESES_CURTOS[m - 1])
            ws.cell(17, 1 + m, f"={col}5")
            ws.cell(18, 1 + m, f"=IF({m}<=MesesFechados,{col}6,NA())")
        for rr in (16, 17, 18):
            ws.row_dimensions[rr].hidden = True
        graf = LineChart()
        graf.title = "Faturamento: previsto x realizado"
        graf.height, graf.width = 9.5, 31
        graf.y_axis.number_format = '#,##0'
        graf.x_axis.delete = False
        graf.y_axis.delete = False
        graf.legend.position = "t"
        graf.title.overlay = False
        linha_grade = GraphicalProperties(ln=LineProperties(solidFill="E3E6EA", w=6350))
        graf.y_axis.majorGridlines.spPr = linha_grade
        for eixo in (graf.x_axis, graf.y_axis):
            eixo.spPr = GraphicalProperties(ln=LineProperties(solidFill="9AA1AA", w=6350))
        graf.visible_cells_only = False
        graf.display_blanks = "gap"
        graf.add_data(Reference(ws, min_col=1, max_col=13, min_row=17, max_row=18), from_rows=True, titles_from_data=True)
        graf.set_categories(Reference(ws, min_col=2, max_col=13, min_row=16))
        previsto, realizado = graf.series
        previsto.tx.strRef = None
        realizado.tx.strRef = None
        from openpyxl.chart.series import SeriesLabel
        previsto.tx = SeriesLabel(v="Previsto")
        realizado.tx = SeriesLabel(v="Realizado")
        previsto.graphicalProperties.line.solidFill = "9AA0A8"
        previsto.graphicalProperties.line.dashStyle = "dash"
        previsto.graphicalProperties.line.width = 22000
        previsto.smooth = False
        realizado.graphicalProperties.line.solidFill = "15171A"
        realizado.graphicalProperties.line.width = 32000
        realizado.marker.symbol = "circle"
        realizado.marker.size = 7
        realizado.marker.graphicalProperties.solidFill = "C9A227"
        realizado.marker.graphicalProperties.line.solidFill = "15171A"
        realizado.smooth = False
        ws.add_chart(graf, "A20")


    # ------------------------------------------------------------------ gerar
    def gerar(self, caminho, *, lancamentos, ajustes, orcamento, saldos, auditoria, meses_fechados=9, dre_manual=()):
        self.wb.active.title = "Capa"  # preenchida no fim: os indicadores dependem das posições da DRE
        self._cadastros(ajustes, orcamento, saldos, auditoria)
        self._lancamentos(lancamentos)
        self._dfc()
        self._dre()
        self._dre_manual(dre_manual)
        self._resumo()
        self._faturamento()
        self._capa(meses_fechados)
        ordem = ["Capa", "Lançamentos", "DFC", "DRE", "DRE Manual", "RESUMO", "Faturamento", "Plano de Contas", "Grupos",
                 "Bancos", "Saldos Informados", "Ajustes DRE", "Orçamento", "Auditoria"]
        self.wb._sheets = [self.wb[n] for n in ordem]
        cores = {"Capa": NOITE, "Lançamentos": "5B7083", "DRE Manual": "C9A227", "DFC": R_CAB, "DRE": R_CAB,
                 "RESUMO": R_CAB, "Faturamento": R_CAB}
        for n in ordem:
            self.wb[n].sheet_properties.tabColor = cores.get(n, PRATA)
        self.wb.calculation.fullCalcOnLoad = True
        self.wb.save(caminho)
        return self.pos
