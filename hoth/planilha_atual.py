"""Lê de volta o conteúdo da planilha Hoth em uso (cadastros e dados), para o app e para reconstruir
as abas de demonstrativos quando o plano de contas muda."""
import datetime as dt
from dataclasses import dataclass, field

from .arquivo import abrir_planilha

from .estrutura import Banco, Conta, Estrutura, Grupo
from .texto import chave

ABAS_GERADAS = ["Capa", "Lançamentos", "DFC", "DRE", "DRE Manual", "RESUMO", "Faturamento", "Plano de Contas",
                "Grupos", "Bancos", "Saldos Informados", "Ajustes DRE", "Orçamento", "Auditoria"]


@dataclass
class Conteudo:
    estrutura: Estrutura
    lancamentos: list = field(default_factory=list)
    ajustes: list = field(default_factory=list)
    orcamento: list = field(default_factory=list)
    saldos: list = field(default_factory=list)
    auditoria: list = field(default_factory=list)
    dre_manual: list = field(default_factory=list)
    meses_fechados: int = 9
    abas_extras: list = field(default_factory=list)


def _tabela(ws) -> list[dict]:
    linhas = ws.iter_rows(values_only=True)
    cab = [c for c in next(linhas)]
    return [dict(zip(cab, r)) for r in linhas if any(v not in (None, "") for v in r)]


def _data(v):
    return v.date() if isinstance(v, dt.datetime) else v


def ler(caminho) -> Conteudo:
    wb = abrir_planilha(caminho, read_only=True, data_only=True)
    try:
        valores_capa = {}
        for linha in wb["Capa"].iter_rows(values_only=True):
            for i, v in enumerate(linha):
                if v in ("Empresa", "Ano base", "Meses fechados") and v not in valores_capa:
                    valores_capa[v] = next((x for x in linha[i + 1:] if x not in (None, "")), None)
        grupos = [Grupo(str(g["Código"]), g["Grupo"], g["Natureza"], g["Entra DRE"] == "Sim", g["Entra DFC"] == "Sim",
                        g["Resultado após o grupo"] or "", g["Base %"] == "Sim") for g in _tabela(wb["Grupos"])]
        cod_grupo = {g.nome: g.codigo for g in grupos}
        contas = []
        for c in _tabela(wb["Plano de Contas"]):
            contas.append(Conta(
                str(c["Código"]), c["Conta"], cod_grupo.get(c["Grupo"], ""), cod_grupo.get(c["Grupo DRE"] or "", ""),
                entra_dfc=c["Entra DFC"] == "Sim", entra_dre=c["Entra DRE"] == "Sim",
                fixo_variavel=c["Fixo/Variável"] or "", ativa=c["Ativa"] != "Não", ordem=int(c.get("Ordem DFC") or 0),
                ordem_dre=int(c.get("Ordem DRE") or 0), dre_manual=c["Valor na DRE"] == "Manual",
                observacao=c["Observação"] or ""))
        bancos = [Banco(b["Banco"], b["Tipo"], float(b["Saldo inicial"] or 0), b["Ativo"] != "Não")
                  for b in _tabela(wb["Bancos"])]
        est = Estrutura(grupos, contas, bancos, empresa=valores_capa.get("Empresa", ""),
                        ano=int(valores_capa.get("Ano base") or dt.date.today().year))
        cont = Conteudo(est, meses_fechados=int(valores_capa.get("Meses fechados") or 9))
        for l in _tabela(wb["Lançamentos"]):
            cont.lancamentos.append({
                "id": str(l["ID"]) if l["ID"] is not None else "", "banco": l["Banco"], "data": _data(l["Data"]),
                "descricao": l["Descrição"] or "", "documento": l["Documento"] or "", "valor": l["Valor"] or 0.0,
                "conta": l["Conta"] or "", "codigo": l["Código"] or "", "grupo": l["Grupo"] or "",
                "origem": l["Origem"] or "", "referencia": l["Referência"] or "", "observacao": l["Observação"] or "",
                "importado_em": l["Importado em"]})
        cont.ajustes = [{"ano": a["Ano"], "mes": a["Mês"], "conta": a["Conta"], "tipo": a["Tipo"], "valor": a["Valor"],
                         "motivo": a["Motivo"] or ""} for a in _tabela(wb["Ajustes DRE"])]
        cont.orcamento = [{"ano": o["Ano"], "mes": o["Mês"], "conta": o["Conta"], "valor": o["Valor"]}
                          for o in _tabela(wb["Orçamento"])]
        cont.saldos = [{"banco": s["Banco"], "ano": s["Ano"], "mes": s["Mês"], "saldo": s["Saldo inicial informado"]}
                       for s in _tabela(wb["Saldos Informados"])]
        cont.auditoria = [[a["Data/hora"], a["Ação"], a["Detalhe"], a["Linhas"], a["Arquivo"], a["Backup"]]
                          for a in _tabela(wb["Auditoria"])]
        nome_por_codigo = {c.codigo: c.nome for c in contas}
        for r in wb["DRE Manual"].iter_rows(min_row=6, values_only=True):
            if not r[0] or str(r[0]) not in nome_por_codigo:
                continue
            for m in range(1, 13):
                v = r[2 + m]
                if v is not None:
                    cont.dre_manual.append({"ano": est.ano, "mes": m, "conta": nome_por_codigo[str(r[0])], "valor": v})
        cont.abas_extras = [n for n in wb.sheetnames if n not in ABAS_GERADAS]
        return cont
    finally:
        wb.close()


def aplicar_renomeacoes(cont: Conteudo, mapa: dict[str, str]):
    """Troca nomes de conta (antigo -> novo) em todos os dados. Usado em renomear e mesclar."""
    if not mapa:
        return
    por_chave = {chave(k): v for k, v in mapa.items()}
    for lista in (cont.lancamentos, cont.ajustes, cont.orcamento, cont.dre_manual):
        for item in lista:
            novo = por_chave.get(chave(item.get("conta")))
            if novo is not None:
                item["conta"] = novo
