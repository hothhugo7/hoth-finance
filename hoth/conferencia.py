"""Confere a planilha Hoth recalculada contra os valores da planilha antiga."""
import re
from collections import defaultdict

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter as L

from .arquivo import abrir_planilha
from .texto import chave

TOL = 0.01
GRUPOS_ENTRADA_DFC_ANTIGA = {"01", "08"}  # na DFC antiga, só essas linhas liam a coluna E da Caixa Loja
CAUSA_CAIXA_LOJA = "Caixa Loja: valor lançado na coluna (ENTRADA/SAÍDA) que a DFC antiga não lia para esta conta"

RESULTADOS_ANTIGOS = {
    "RECEITA LÍQUIDA ( = )": "RECEITA LIQUIDA ( = )",
    "MARGEM DE CONTRIBUIÇÃO ( = )": "RESULTADO OPERACIONAL BRUTO ( = ) MG CONTRIBUICAO",
    "EBITDA - LUCRO OPERACIONAL ( = )": "RESULTADO OPERACIONAL ( = )",
    "EBIT - LUCRO LÍQUIDO ( = )": "RESULTADO LIQUIDO ( = )",
    "RESULTADO LÍQUIDO CAIXA ( = )": "RESULTADO LIQUIDO CAIXA ( = )",
}


def _v(x):
    return float(x) if isinstance(x, (int, float)) else 0.0


class Conferencia:
    def __init__(self, caminho_novo, migracao, pos, meses_fechados=9):
        self.m, self.pos, self.meses_fechados = migracao, pos, meses_fechados
        self.wb = abrir_planilha(caminho_novo, data_only=True)
        self.contas = {c.codigo: c for c in migracao.estrutura.contas}
        self._causas()

    def _causas(self):
        """Diferenças esperadas: o que a planilha antiga contava diferente da nova."""
        self.causa_dfc = defaultdict(lambda: defaultdict(float))  # (conta, mês) -> {causa: diferença esperada}
        grupo = {c.nome: c.grupo for c in self.m.estrutura.contas}
        for l in self.m.lancamentos:
            if not l["conta"]:
                continue
            mes = l["data"].month
            if l["banco"] == "Caixa Loja" and (l["valor"] > 0) != (grupo[l["conta"]] in GRUPOS_ENTRADA_DFC_ANTIGA):
                self.causa_dfc[(l["conta"], mes)][CAUSA_CAIXA_LOJA] += l["valor"]
            antigo = l.get("mes_planilha_antiga")
            if antigo:
                txt = f"{l['referencia']}: coluna MÊS digitada {antigo} na planilha antiga, mas a data é {l['data']:%d/%m}"
                self.causa_dfc[(l["conta"], mes)][txt] += l["valor"]
                self.causa_dfc[(l["conta"], antigo)][txt] -= l["valor"]
        self.erros_por_mes = defaultdict(list)
        for e in self.m.erros_formula:
            mt = re.search(r"\((.+), mês (\d+)\)", e)
            if mt:
                self.erros_por_mes[(mt.group(1), int(mt.group(2)))].append(e)

    def _explicar(self, nome, mes, diferenca):
        causas = self.causa_dfc.get((nome, mes), {})
        if causas and abs(diferenca - sum(causas.values())) <= TOL:
            return list(causas)
        return []

    def _linhas_por_codigo(self, aba, col_valor):
        ws = self.wb[aba]
        out = {}
        for r in range(1, ws.max_row + 1):
            cod = ws.cell(r, 2).value
            if isinstance(cod, str) and re.fullmatch(r"\d\d\.\d\d", cod):
                out[cod] = {m: _v(ws.cell(r, col_valor(m)).value) for m in range(1, 13)}
        return out

    def comparar(self):
        dfc_nova = self._linhas_por_codigo("DFC", lambda m: 2 + m)
        col_mes = self.pos["dre_col_mes"]
        dre_nova = self._linhas_por_codigo("DRE", lambda m: col_mes[m] + 1)
        self.dif_dfc, self.dif_dre = [], []
        self.qtd_dfc = self.qtd_dre = 0
        for cod, serie in dfc_nova.items():
            nome = self.contas[cod].nome
            antiga = self.m.dfc_antiga.get(nome)
            for mes in range(1, 13):
                velha = antiga[mes] if antiga else 0.0
                self.qtd_dfc += 1
                if abs(serie[mes] - velha) > TOL:
                    causa = self._explicar(nome, mes, serie[mes] - velha)
                    if antiga is None:
                        causa.append("Conta sem linha na DFC antiga")
                    self.dif_dfc.append([cod, nome, mes, velha, serie[mes], serie[mes] - velha, "; ".join(causa)])
        for cod, serie in dre_nova.items():
            nome = self.contas[cod].nome
            antiga = self.m.dre_antiga.get(nome)
            for mes in range(1, 13):
                velha = antiga[mes] if antiga else 0.0
                self.qtd_dre += 1
                if abs(serie[mes] - velha) > TOL:
                    causa = list(self.erros_por_mes.get((nome, mes), [])) + self._explicar(nome, mes, serie[mes] - velha)
                    comp = self.m.compensacoes_removidas.get((nome, mes))
                    if comp is not None and abs((serie[mes] - velha) + comp) <= TOL:
                        causa.append(f"Compensação de pró-labore removida ({_brl(comp)}): a retirada entra pelo valor "
                                     "pago e o pró-labore é digitado na aba DRE Manual")
                    if nome in self.m.incluidas_na_dre and abs(velha) <= TOL:
                        causa.append("Conta incluída na DRE por decisão do usuário (a DRE antiga não somava)")
                    if abs(serie[mes] + velha) <= TOL:
                        causa.append("Mesmo valor com sinal invertido (a DRE antiga digitava positivo)")
                    self.dif_dre.append([cod, nome, mes, velha, serie[mes], serie[mes] - velha,
                                         "; ".join(causa) or "Verificar"])
        self._totais()

    def _totais(self):
        dfc, dre = self.wb["DFC"], self.wb["DRE"]
        self.totais = []
        antigos = {chave(k): v for k, v in self.m.dfc_antiga_totais.items()}
        pares = [("TOTAL DE ENTRADAS", self.pos["dfc_entradas"], "TOTAL DE ENTRADAS ( = )"),
                 ("TOTAL DE SAÍDAS", self.pos["dfc_saidas"], "TOTAL DE SAIDAS (-)"),
                 ("MOVIMENTAÇÕES", self.pos["dfc_movimentacoes"], None),
                 ("MOVIMENTO DO MÊS", self.pos["dfc_movimento"], None),
                 ("SALDO FINAL", self.pos["dfc_saldo_final"], "SALDO FINAL")]
        for nome, r, k_antigo in pares:
            velho = antigos.get(k_antigo, {}) if k_antigo else {}
            for mes in range(1, 13):
                novo = _v(dfc.cell(r, 2 + mes).value)
                self.totais.append(["DFC", nome, mes, velho.get(mes) if k_antigo else None, novo])
        col_mes = self.pos["dre_col_mes"]
        antigos = {chave(k): v for k, v in self.m.dre_antiga_totais.items()}
        for chave_pos, r in self.pos.items():
            if not isinstance(chave_pos, tuple):
                continue
            tipo, nome = chave_pos
            if tipo == "dre_grupo":
                rotulo, velho = f"Grupo {nome} - {self.m.estrutura.grupo(nome).nome}", antigos.get(f"GRUPO {nome}", {})
            elif tipo == "dre_resultado":
                rotulo, velho = nome, antigos.get(chave(RESULTADOS_ANTIGOS.get(nome, nome)), {})
            else:
                continue
            for mes in range(1, 13):
                self.totais.append(["DRE", rotulo, mes, velho.get(mes), _v(dre.cell(r, col_mes[mes] + 1).value)])

    def _situacao(self, t):
        demo, nome, mes, antigo, novo = t
        if antigo is None:
            return "Sem linha equivalente na planilha antiga"
        if abs(antigo - novo) <= TOL:
            return "Igual"
        if abs(antigo + novo) <= TOL:
            return "Igual com sinal invertido (a planilha antiga mostrava a despesa positiva)"
        if mes > self.meses_fechados:
            return "Diferente - mês em aberto na planilha antiga"
        if demo == "DFC" and nome == "SALDO FINAL":
            return "Diferente - a DFC antiga usa saldo inicial digitado a cada mês; a nova acumula o saldo"
        contas = self._diferenca_contas(demo, nome, mes)
        if contas is None:
            return "Diferente"
        residuo = round((novo - antigo) - contas, 2)
        partes = []
        if abs(contas) > TOL:
            partes.append(f"{_brl(contas)} vêm das contas com diferença (abas DFC/DRE diferenças)")
        if abs(residuo) > TOL:
            formula = self.m.dre_antiga_formulas.get(chave(RESULTADOS_ANTIGOS.get(nome, nome)), {}).get(mes)
            if demo == "DRE" and formula:
                partes.append(f"{_brl(residuo)} vêm de erro de sinal na fórmula antiga do mês ({formula}); "
                              "a fórmula muda de mês para mês e às vezes subtrai valores que já são negativos")
            else:
                return "Diferente - " + "; ".join(partes + [f"{_brl(residuo)} sem causa identificada"])
        return "Diferente - " + "; ".join(partes)

    def _diferenca_contas(self, demo, nome, mes):
        """Soma das diferenças das contas que compõem a linha de total, no mês."""
        grupos = [g for g in self.m.estrutura.grupos]
        if demo == "DFC":
            natureza = {"TOTAL DE ENTRADAS": "Entrada", "TOTAL DE SAÍDAS": "Saída",
                        "MOVIMENTAÇÕES": "Movimentação"}.get(nome)
            if natureza is None:
                return None
            cods = {g.codigo for g in grupos if g.natureza == natureza}
            return sum(d[5] for d in self.dif_dfc if d[2] == mes and self.contas[d[0]].grupo in cods)
        if nome.startswith("Grupo "):
            cods = {nome.split()[1]}
        else:
            ordem = [g for g in grupos if g.entra_dre]
            fim = next((i for i, g in enumerate(ordem) if g.resultado_apos == nome), None)
            if fim is None:
                return None
            cods = {g.codigo for g in ordem[:fim + 1]}
        return sum(d[5] for d in self.dif_dre if d[2] == mes and self.contas[d[0]].grupo_na_dre in cods
                   and not abs(d[4] + d[3]) <= TOL)  # sinal invertido não muda o grupo

    # ----------------------------------------------------------------- relatório
    def salvar(self, caminho):
        m = self.m
        wb = openpyxl.Workbook()
        cab_font, cab_fill = Font(bold=True, color="C9CDD2"), PatternFill("solid", fgColor="1E1F22")

        def aba(nome, cab, linhas, larguras):
            ws = wb.create_sheet(nome)
            ws.append(cab)
            for c in ws[1]:
                c.font, c.fill = cab_font, cab_fill
            for l in linhas:
                ws.append(l)
            for i, w in enumerate(larguras, start=1):
                ws.column_dimensions[L(i)].width = w
            ws.freeze_panes = "A2"
            for row in ws.iter_rows(min_row=2):
                for c in row:
                    if isinstance(c.value, float):
                        c.number_format = '#,##0.00;[Red]-#,##0.00'
            return ws

        ws = wb.active
        ws.title = "Resumo"
        ws.column_dimensions["A"].width = 70
        ws.column_dimensions["B"].width = 18
        sem_causa_dfc = [d for d in self.dif_dfc if not d[6]]
        sem_causa_dre = [d for d in self.dif_dre if d[6] == "Verificar"]
        linhas = [
            ("Lançamentos de 2026 migrados", len(m.lancamentos)),
            ("Lançamentos sem conta (pendentes)", sum(1 for l in m.lancamentos if not l["conta"])),
            ("Linhas antigas descartadas (valor zero, sem data ou de outro ano)", len(m.descartados)),
            ("Contas no plano novo", len(m.estrutura.contas)),
            ("Ajustes manuais da DRE migrados", len(m.ajustes)),
            ("Valores de orçamento (PREV) migrados", len(m.orcamento)),
            ("", ""),
            ("DFC: células conta x mês comparadas", self.qtd_dfc),
            ("DFC: células com diferença", len(self.dif_dfc)),
            ("DFC: diferenças sem causa identificada", len(sem_causa_dfc)),
            ("DRE: células conta x mês comparadas", self.qtd_dre),
            ("DRE: células com diferença", len(self.dif_dre)),
            ("DRE: diferenças sem causa identificada", len(sem_causa_dre)),
            ("", ""),
            ("Erros de fórmula encontrados na DRE antiga", len(m.erros_formula)),
            ("Linhas duplicadas na DFC antiga (somadas duas vezes)", ", ".join(m.dfc_antiga_duplicadas) or "nenhuma"),
        ]
        for i, (k, v) in enumerate(linhas, start=1):
            ws.cell(i, 1, k)
            ws.cell(i, 2, v)

        aba("DFC diferenças", ["Código", "Conta", "Mês", "Planilha antiga", "Planilha Hoth", "Diferença", "Causa"],
            self.dif_dfc, [8, 46, 6, 16, 16, 14, 70])
        aba("DRE diferenças", ["Código", "Conta", "Mês", "Planilha antiga", "Planilha Hoth", "Diferença", "Causa"],
            self.dif_dre, [8, 46, 6, 16, 16, 14, 90])
        aba("Totais", ["Demonstrativo", "Linha", "Mês", "Planilha antiga", "Planilha Hoth", "Situação"],
            [t + [self._situacao(t)] for t in self.totais], [12, 52, 6, 18, 18, 110])
        aba("Ajustes DRE migrados", ["Ano", "Mês", "Conta", "Tipo", "Valor", "Motivo"],
            [[a["ano"], a["mes"], a["conta"], a["tipo"], a["valor"], a["motivo"]] for a in m.ajustes],
            [6, 5, 44, 11, 14, 90])
        aba("Classificações", ["Classificação na planilha antiga", "Conta no plano novo", "Lançamentos"],
            [[k[0], k[1] or "(sem conta)", v] for k, v in sorted(m.classificacoes.items(), key=lambda x: -x[1])],
            [52, 52, 12])
        aba("Descartados", ["Aba", "Linha", "Motivo", "Descrição", "Valor"],
            [[d["aba"].strip(), d["linha"], d["motivo"], d.get("descricao"), d.get("valor")] for d in m.descartados],
            [18, 8, 22, 60, 14])
        aba("Avisos", ["Tipo", "Detalhe"],
            [["Erro de fórmula na DRE antiga", e] for e in m.erros_formula]
            + [["Aviso de leitura", a] for a in m.avisos]
            + [["Conta renomeada", f"{k} -> {v}"] for k, v in m.estrutura.renomeacoes.items()]
            + [["Lançamento sem conta", f"{l['referencia']}: {l['descricao']} ({l['valor']:.2f})"]
               for l in m.lancamentos if not l["conta"]],
            [32, 120])
        wb.save(caminho)
        return {"dif_dfc": len(self.dif_dfc), "dif_dre": len(self.dif_dre),
                "sem_causa_dfc": len(sem_causa_dfc), "sem_causa_dre": len(sem_causa_dre)}


def _brl(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
