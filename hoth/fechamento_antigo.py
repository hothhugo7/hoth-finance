"""Leitura da planilha antiga "01. FECHAMENTO FINANCEIRO EXEMPLO - 2026.xlsx".

Só lê. Produz a estrutura (grupos, contas, bancos), os lançamentos de 2026, os
ajustes manuais escondidos nas fórmulas da DRE, o orçamento (PREV) e os valores
calculados da DRE/DFC antigas para a conferência.
"""
import datetime as dt
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

from .estrutura import BANCOS_PADRAO, GRUPOS_PADRAO, Banco, Conta, Estrutura
from .texto import chave, id_lancamento, limpar

ABAS_BANCO = {
    "Santander": "Santander",
    "Cora": "Cora",
    "Caixa Loja": "Caixa Loja",
    "Caixa Economica 1 ": "Caixa Econômica 1",
    "Caixa Economica 2": "Caixa Econômica 2",
}

# Cabeçalhos de grupo na aba "Plano Contas" (coluna C) e na DRE antiga (coluna A).
GRUPO_POR_NOME = {
    "FATURAMENTO BRUTO ( = )": "01",
    "IMPOSTOS SOB RECEITAS ( - )": "02",
    "CPV (CUSTO PROD. VENDIDO) ( - )": "03",
    "CUSTO INDIRETO": "04",
    "CUSTOS INDIRETOS": "04",
    "DESPESAS COMERCIAIS ( - )": "05",
    "DESP. ADMINISTRATIVAS ( - )": "06",
    "DESP. C/ PESSOAL ( - )": "07",
    "RECEITAS NAO OPERACIONAIS ( + )": "08",
    "DESPESAS NAO OPERACIONAIS ( - )": "09",
    "BENS E AQUISICOES ( - )": "10",
    "DISTRIBUICAO DE LUCROS ( - )": "11",
    "MOVIMENTACOES BANCARIAS": "12",
}

# Nomes duplicados no plano antigo: (grupo, nome antigo) -> nome novo.
RENOMEAR = {
    ("02", "IRRF"): "IRRF S/ RECEITA",
    ("07", "FREELANCE"): "FREELANCE (PESSOAL)",
}

# Linhas da DRE antiga sem conta correspondente e sempre zeradas.
DRE_IGNORAR = {"IRPJ -", "CSLL -", ""}

# Contas que só afetam o caixa (DFC), nunca a DRE (definido pelo usuário em 21/10/2026).
SO_DFC = {
    "DEVOLUCAO DE VALOR": "Só DFC: repasse das vendas feitas por terceiros na maquininha alugada (valor menos a taxa)",
}

# Contas que a DRE antiga não somava (célula vazia), mas que passam a entrar na DRE (decisão do usuário).
INCLUIR_NA_DRE = {"RETIRADA JOSE"}

# Contas da DRE com valor digitado (aba DRE Manual), definidas pelo usuário em 21/10/2026.
# Além destas, o pró-labore de cada sócio.
DRE_MANUAL = {
    "FATURAMENTO - VENDAS REALIZADAS",          # faturamento bruto por competência (Curva ABC)
    "CUSTO DO PRODUTO VENDIDO (FORNECEDOR)",    # CPV
    "COPA E COZINHA",
    "TARIFAS DE MAQUININHAS CIELO",
    "TARIFAS DE MAQUININHAS REDE",
    "CARTAO DE CREDITO (TARIFAS)",
}

# Retiradas que não são de um sócio específico (não geram linha de pró-labore).
RETIRADAS_GERAIS = {"RETIRADA DOS SOCIOS", "RETIRADA CONJUNTA"}

# Linhas da DFC antiga que não estão no plano de contas, mas recebem lançamentos.
DFC_EXTRAS = {
    "SISTEMA S": "07",
    "RESGATE DE APLICACAO ( - )": "12",
    "AJUSTE DE SALDO": "12",
    "OUTRAS SAIDAS ( - )": "12",
}

# Linhas de saldo da DFC antiga -> banco.
DFC_SALDOS = {
    "SANTANDER": "Santander", "CAIXA ECONOMICA 1": "Caixa Econômica 1", "CAIXA ECONOMICA 2": "Caixa Econômica 2",
    "CORA": "Cora", "CAIXA LOJA": "Caixa Loja", "SANTANDER CDB": "Santander CDB",
    "SANTANDER CONTAMAX": "Santander Contamax", "CAIXA FUNDO RENDA FIXA": "Caixa Fundo Renda Fixa",
    "CAIXA GIRO EMPRESA": "Caixa Giro Empresa",
}


def _sem_pontuacao(texto: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", chave(texto))


def _numero(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace("R$", "").strip()
        if re.fullmatch(r"-?[\d.]*,\d+", s):
            s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None


@dataclass
class Migracao:
    estrutura: Estrutura
    lancamentos: list = field(default_factory=list)      # dicts
    ajustes: list = field(default_factory=list)          # dicts: ano, mes, conta, tipo, valor, motivo
    orcamento: list = field(default_factory=list)        # dicts: ano, mes, conta, valor
    saldos_informados: list = field(default_factory=list)  # dicts: banco, ano, mes, saldo
    dfc_antiga: dict = field(default_factory=dict)       # conta -> {mes: valor}
    dfc_antiga_duplicadas: list = field(default_factory=list)
    dfc_antiga_totais: dict = field(default_factory=dict)  # rótulo -> {mes: valor}
    dre_antiga: dict = field(default_factory=dict)       # conta -> {mes: valor}
    dre_antiga_totais: dict = field(default_factory=dict)  # rótulo -> {mes: valor}
    dre_antiga_formulas: dict = field(default_factory=dict)  # chave do rótulo -> {mes: fórmula}
    classificacoes: Counter = field(default_factory=Counter)  # (original, conta nova) -> qtd
    descartados: list = field(default_factory=list)      # dicts: aba, linha, motivo
    erros_formula: list = field(default_factory=list)    # textos
    avisos: list = field(default_factory=list)
    incluidas_na_dre: set = field(default_factory=set)
    dre_manual: list = field(default_factory=list)        # dicts: ano, mes, conta, valor
    compensacoes_removidas: dict = field(default_factory=dict)  # (conta, mês) -> valor que a DRE antiga somava
    contas_fora_dre_antiga: Counter = field(default_factory=Counter)  # conta -> total que a DRE antiga não somava


class LeitorFechamento:
    def __init__(self, caminho: str, ano: int = 2026):
        self.ano = ano
        self.wf = openpyxl.load_workbook(caminho)                  # fórmulas
        self.wv = openpyxl.load_workbook(caminho, data_only=True)  # valores calculados pelo Excel
        self.m = Migracao(Estrutura(grupos=[g for g in GRUPOS_PADRAO], contas=[], bancos=[]))
        self.m.estrutura.ano = ano

    # ------------------------------------------------------------------ plano
    def _montar_plano(self):
        est = self.m.estrutura
        pc = self.wv["Plano Contas"]
        seq = Counter()
        self._por_chave = {}
        for r in range(4, pc.max_row + 1):
            nome, grupo_nome = limpar(pc.cell(r, 2).value), limpar(pc.cell(r, 3).value)
            if not nome or not grupo_nome:
                continue
            g = GRUPO_POR_NOME.get(chave(grupo_nome))
            if g is None:
                self.m.avisos.append(f"Plano Contas linha {r}: grupo desconhecido '{grupo_nome}'")
                continue
            nome = nome.upper()
            novo = RENOMEAR.get((g, chave(nome)))
            if novo:
                est.renomeacoes[f"{nome} ({est.grupo(g).nome})"] = novo
                nome = novo
            seq[g] += 1
            conta = Conta(f"{g}.{seq[g]:02d}", nome, g, ordem=1000 + r, entra_dre=False, entra_dfc=False)
            est.contas.append(conta)
            self._por_chave.setdefault(chave(nome), conta)
        self._seq = seq

    def _nova_conta(self, nome: str, grupo: str, **kw) -> Conta:
        self._seq[grupo] += 1
        conta = Conta(f"{grupo}.{self._seq[grupo]:02d}", nome.upper(), grupo, **kw)
        self.m.estrutura.contas.append(conta)
        self._por_chave[chave(conta.nome)] = conta
        return conta

    def conta_por_nome(self, nome) -> Conta | None:
        k = chave(nome)
        if k in self._por_chave:
            return self._por_chave[k]
        sp = _sem_pontuacao(nome)
        for c in self.m.estrutura.contas:
            if _sem_pontuacao(c.nome) == sp:
                return c
        return None

    # -------------------------------------------------------------------- DFC
    def _ler_dfc(self):
        dfc_f, dfc_v = self.wf["DFC"], self.wv["DFC"]
        vistos = Counter()
        saldo_bancos = {}
        for r in range(6, 165):
            rotulo = limpar(dfc_v.cell(r, 2).value)
            if not rotulo:
                continue
            k = chave(rotulo)
            valores = {m: _numero(dfc_v.cell(r, 2 + m).value) or 0.0 for m in range(1, 13)}
            if k in DFC_SALDOS:
                saldo_bancos[DFC_SALDOS[k]] = {
                    m: _numero(dfc_v.cell(r, 2 + m).value) for m in range(1, 13)
                }
                continue
            formula = str(dfc_f.cell(r, 3).value or "")
            if "SUMIFS(" not in formula:
                self.m.dfc_antiga_totais[rotulo] = valores
                continue
            conta = self.conta_por_nome(rotulo)
            if conta is None and k in DFC_EXTRAS:
                conta = self._nova_conta(rotulo.replace("( - )", "").strip(), DFC_EXTRAS[k], ordem=r, entra_dre=False,
                                         observacao="Linha que existia só na DFC antiga")
            if conta is None:
                self.m.avisos.append(f"DFC linha {r}: '{rotulo}' sem conta correspondente")
                continue
            conta.entra_dfc = True
            conta.ordem = r
            vistos[conta.nome] += 1
            if vistos[conta.nome] > 1:
                self.m.dfc_antiga_duplicadas.append(conta.nome)
                continue
            self.m.dfc_antiga[conta.nome] = valores
        for banco in BANCOS_PADRAO:
            serie = saldo_bancos.get(banco.nome, {})
            b = Banco(banco.nome, banco.tipo, saldo_inicial=serie.get(1) or 0.0)
            self.m.estrutura.bancos.append(b)
            for mes, saldo in serie.items():
                if saldo not in (None, 0.0) or mes == 1:
                    self.m.saldos_informados.append(
                        {"banco": b.nome, "ano": self.ano, "mes": mes, "saldo": saldo or 0.0})

    # -------------------------------------------------------------------- DRE
    def _ler_dre(self):
        dre_f, dre_v = self.wf["DRE 2026"], self.wv["DRE 2026"]
        grupo_atual = None
        sinal_grupo = {}
        for r in range(6, 137):
            rotulo = limpar(dre_v.cell(r, 1).value)
            k = chave(rotulo)
            real = {m: dre_v.cell(r, 10 + 4 * (m - 1)).value for m in range(1, 13)}
            if k in GRUPO_POR_NOME:
                grupo_atual = GRUPO_POR_NOME[k]
                sinal_grupo[grupo_atual] = -1 if str(dre_f.cell(r, 10).value or "").startswith("=-SUM") else 1
                self.m.dre_antiga_totais[f"GRUPO {grupo_atual}"] = {m: _numero(v) or 0.0 for m, v in real.items()}
                prev_grupo = {m: _numero(dre_v.cell(r, 9 + 4 * (m - 1)).value) for m in range(1, 13)}
                self._prev_grupo = (grupo_atual, prev_grupo)
                continue
            if k in DRE_IGNORAR or grupo_atual is None:
                continue
            if k in SO_DFC:
                conta = self.conta_por_nome(rotulo)
                if conta:
                    conta.entra_dre, conta.observacao = False, SO_DFC[k]
                continue
            if "( = )" in rotulo or k.startswith(("RESULTADO", "TOTAL")):
                self.m.dre_antiga_totais[rotulo] = {m: _numero(v) or 0.0 for m, v in real.items()}
                self.m.dre_antiga_formulas[k] = {m: str(dre_f.cell(r, 10 + 4 * (m - 1)).value) for m in range(1, 13)}
                continue
            if grupo_atual == "02" and k == "IRRF":
                conta = self._por_chave[chave("IRRF S/ RECEITA")]
            else:
                conta = self.conta_por_nome(rotulo)
            if conta is None:
                conta = self._nova_conta(rotulo, grupo_atual, ordem=r, entra_dfc=False,
                                         observacao="Linha que existia só na DRE antiga (valor manual)")
            if k in DRE_MANUAL or k.startswith("PROLABORE SOCIOS"):
                conta.dre_manual = True
            conta.entra_dre = True
            conta.ordem_dre = r
            if conta.grupo != grupo_atual:
                conta.grupo_dre = grupo_atual
            conta.fixo_variavel = limpar(dre_v.cell(r, 2).value).upper()
            self.m.dre_antiga[conta.nome] = {m: _numero(v) or 0.0 for m, v in real.items()}
            for m in range(1, 13):
                if conta.dre_manual:
                    self._valor_manual(dre_f, dre_v, r, m, conta, grupo_atual)
                else:
                    self._ajuste_da_celula(dre_f, dre_v, r, m, conta, grupo_atual)
                prev = _numero(dre_v.cell(r, 9 + 4 * (m - 1)).value)
                if prev:
                    self.m.orcamento.append({"ano": self.ano, "mes": m, "conta": conta.nome, "valor": prev})
            if self._prev_grupo[0] == grupo_atual and grupo_atual == "01" and k == "FATURAMENTO - VENDAS REALIZADAS":
                for m, prev in self._prev_grupo[1].items():
                    if prev:
                        self.m.orcamento.append({"ano": self.ano, "mes": m, "conta": conta.nome, "valor": prev})
        self.sinal_grupo_dre = sinal_grupo
        self._prolabore_por_socio()

    def _valor_manual(self, dre_f, dre_v, r, m, conta, grupo):
        if dre_f.cell(r, 10 + 4 * (m - 1)).value is None:
            return
        valor = _numero(dre_v.cell(r, 10 + 4 * (m - 1)).value) or 0.0
        if self.m.estrutura.grupo(grupo).natureza == "Saída":
            valor = -abs(valor)
        self.m.dre_manual.append({"ano": self.ano, "mes": m, "conta": conta.nome, "valor": round(valor, 2)})

    def _prolabore_por_socio(self):
        """Uma linha de pró-labore (valor manual na DRE) para cada sócio que tem conta de retirada."""
        est = self.m.estrutura
        existentes = [c for c in est.contas if chave(c.nome).startswith("PROLABORE SOCIOS")]
        ordem = max((c.ordem_dre for c in existentes), default=0)
        for c in [c for c in est.contas if c.grupo == "09" and chave(c.nome).startswith("RETIRADA ")]:
            if chave(c.nome) in RETIRADAS_GERAIS:
                continue
            socio = c.nome.split(" ", 1)[1]
            nome = f"PROLABORE SÓCIOS {socio}"
            pl = self.conta_por_nome(nome) or self._nova_conta(
                nome, "07", ordem=900, observacao="Criada para ter uma linha de pró-labore por sócio")
            pl.entra_dre = pl.entra_dfc = pl.dre_manual = True
            if not pl.ordem_dre:
                pl.ordem_dre = ordem
            pl.fixo_variavel = pl.fixo_variavel or "FIXO"

    def _ajuste_da_celula(self, dre_f, dre_v, r, m, conta, grupo):
        col = 10 + 4 * (m - 1)
        f = dre_f.cell(r, col).value
        letra = get_column_letter(col)
        if f is None:
            # Célula vazia: a DRE antiga não somava os lançamentos desta conta neste mês.
            if chave(conta.nome) in INCLUIR_NA_DRE:
                self.m.incluidas_na_dre.add(conta.nome)
                return
            if m <= self._ultimo_mes and round(self._total_lanc.get((conta.nome, m), 0.0), 2):
                self.m.ajustes.append({"ano": self.ano, "mes": m, "conta": conta.nome, "tipo": "SUBSTITUI", "valor": 0.0,
                                       "motivo": f"Célula {letra}{r} vazia na DRE antiga: os lançamentos desta conta "
                                                 f"não entravam na DRE. Apague este ajuste para passar a considerar."})
                self.m.contas_fora_dre_antiga[conta.nome] += round(self._total_lanc[(conta.nome, m)], 2)
            return
        if isinstance(f, (int, float)):
            valor = float(f)
            if self.m.estrutura.grupo(grupo).natureza == "Saída":
                valor = -abs(valor)
            self.m.ajustes.append({"ano": self.ano, "mes": m, "conta": conta.nome, "tipo": "SUBSTITUI",
                                   "valor": valor, "motivo": f"Valor digitado na DRE antiga ({letra}{r})"})
            return
        f = str(f)
        if re.fullmatch(r"=[\d\s.+\-*/()]+", f):
            valor = _numero(dre_v.cell(r, col).value) or 0.0
            if self.m.estrutura.grupo(grupo).natureza == "Saída":
                valor = -abs(valor)
            self.m.ajustes.append({"ano": self.ano, "mes": m, "conta": conta.nome, "tipo": "SUBSTITUI",
                                   "valor": valor, "motivo": f"Conta digitada na DRE antiga ({letra}{r}: {f[1:]})"})
            return
        mt = re.fullmatch(r"=SUMIFS\(DFC!\$([A-Z]+):\$[A-Z]+,DFC!\$B:\$B,'DRE 2026'!\$A\d+\)(.*)", f)
        if not mt:
            self.m.avisos.append(f"DRE {letra}{r} ({conta.nome}): fórmula não reconhecida {f[:80]}")
            return
        col_dfc, resto = mt.group(1), mt.group(2).strip()
        mes_dfc = column_index_from_string(col_dfc) - 2
        if mes_dfc != m:
            self.m.erros_formula.append(
                f"DRE {letra}{r} ({conta.nome}, mês {m}) soma a DFC do mês {mes_dfc} (coluna {col_dfc})")
        if not resto:
            return
        if re.search(r"[A-Z]+\$?\d", resto):
            # Ex.: Retirada Gustavo "-J73": compensava a provisão do pró-labore. O pró-labore agora é digitado à
            # parte (DRE Manual) e a retirada entra pelo valor pago, então a compensação não é migrada.
            valor = round(_numero(dre_v.cell(r, col).value) or 0.0, 2)
            base = round(self._total_lanc.get((conta.nome, m), 0.0), 2)
            if abs(valor - base) > 0.005:
                self.m.compensacoes_removidas[(conta.nome, m)] = round(valor - base, 2)
            return
        expr = re.sub(r"\$?([A-Z]{1,2})\$?(\d+)",
                      lambda x: repr(_numero(dre_v[f"{x.group(1)}{x.group(2)}"].value) or 0.0), resto)
        if not re.fullmatch(r"[\d\s.+\-*/()e]+", expr):
            self.m.avisos.append(f"DRE {letra}{r}: ajuste não reconhecido '{resto}'")
            return
        valor = round(eval(expr), 2)  # só dígitos e operadores, validado acima
        if valor:
            self.m.ajustes.append({"ano": self.ano, "mes": m, "conta": conta.nome, "tipo": "SOMA",
                                   "valor": valor, "motivo": f"Ajuste escrito na fórmula da DRE antiga ({letra}{r}: {resto})"})

    # ------------------------------------------------------------ lançamentos
    def _ler_lancamentos(self):
        for aba, banco in ABAS_BANCO.items():
            ws = self.wv[aba]
            ocorrencias = Counter()
            for i, row in enumerate(ws.iter_rows(min_row=4, max_col=6, values_only=True), start=4):
                data, mes_antigo, desc, classe, e, f = row
                if data is None and desc is None and e is None and f is None:
                    continue
                if not isinstance(data, (dt.datetime, dt.date)):
                    self.m.descartados.append({"aba": aba, "linha": i, "motivo": "sem data", "descricao": desc})
                    continue
                data = data.date() if isinstance(data, dt.datetime) else data
                if data.year != self.ano:
                    self.m.descartados.append({"aba": aba, "linha": i, "motivo": f"data de {data.year}",
                                               "descricao": desc, "valor": _numero(e) or _numero(f)})
                    continue
                ve, vf = _numero(e), _numero(f)
                if aba == "Caixa Loja":
                    valor = (ve or 0.0) + (vf or 0.0)   # entradas em E (+), saídas em F (−)
                else:
                    valor = (ve or 0.0) - (vf or 0.0)   # valor com sinal em E
                valor = round(valor, 2)
                if valor == 0:
                    self.m.descartados.append({"aba": aba, "linha": i, "motivo": "valor zero ou vazio",
                                               "descricao": desc})
                    continue
                original = limpar(classe)
                conta = self.conta_por_nome(original) if original else None
                self.m.classificacoes[(original, conta.nome if conta else "")] += 1
                descricao = limpar(desc)
                k = (data, valor, chave(descricao))
                ocorrencias[k] += 1
                self.m.lancamentos.append({
                    "id": id_lancamento(banco, data, valor, descricao, "", ocorrencias[k]),
                    "banco": banco, "data": data, "descricao": descricao, "documento": "",
                    "valor": valor, "conta": conta.nome if conta else "",
                    "origem": "Histórico planilha antiga" if conta else "",
                    "referencia": f"{aba.strip()}!A{i}",
                    "observacao": "" if conta or not original else f"Classificação antiga não encontrada no plano: {original}",
                })
                if not conta and chave(descricao) == "AJUSTE DE SALDO":
                    self.m.lancamentos[-1]["observacao"] = ("Sem classificação de propósito: só acerta o saldo do banco "
                                                            "(decisão do usuário em 21/10/2026)")
                if isinstance(mes_antigo, (int, float)) and int(mes_antigo) != data.month:
                    self.m.lancamentos[-1]["mes_planilha_antiga"] = int(mes_antigo)
        self.m.lancamentos.sort(key=lambda l: (l["data"], l["banco"]))

    def ler(self) -> Migracao:
        self._montar_plano()
        self._ler_dfc()
        self._ler_lancamentos()
        self._total_lanc = defaultdict(float)
        for l in self.m.lancamentos:
            if l["conta"]:
                self._total_lanc[(l["conta"], l["data"].month)] += l["valor"]
        self._ultimo_mes = max(l["data"].month for l in self.m.lancamentos)
        self._ler_dre()
        est = self.m.estrutura
        for c in est.contas:
            if not c.entra_dfc and not c.entra_dre:
                c.entra_dfc = True  # conta do plano sem linha em nenhum demonstrativo: passa a aparecer na DFC
                c.observacao = c.observacao or "Não tinha linha na DFC nem na DRE antigas"
        return self.m
