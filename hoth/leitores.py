"""Leitores dos extratos: Santander (.xlsx), Cora (.ofx) e boletos da lotérica do RET (.xls).

Cada leitor devolve lançamentos no mesmo formato da aba Lançamentos, com a descrição
montada igual à do histórico da planilha (para o aprendizado reconhecer).
"""
import datetime as dt
import os
import re
from collections import Counter
from pathlib import Path

import openpyxl

from .texto import chave, id_lancamento, limpar


def _data_br(texto) -> dt.date:
    if isinstance(texto, dt.datetime):
        return texto.date()
    if isinstance(texto, dt.date):
        return texto
    return dt.datetime.strptime(str(texto).strip(), "%d/%m/%Y").date()


def _com_ids(banco: str, linhas: list[dict]) -> list[dict]:
    """Atribui o ID estável. O documento fica fora do ID para casar com o histórico migrado, que não tinha
    documento; lançamentos iguais no mesmo dia são separados pela ordem de ocorrência."""
    ocorrencias = Counter()
    for l in linhas:
        k = (l["data"], l["valor"], chave(l["descricao"]))
        ocorrencias[k] += 1
        l["id"] = id_lancamento(banco, l["data"], l["valor"], l["descricao"], "", ocorrencias[k])
    return linhas


def ler_extrato_santander(caminho) -> dict:
    """Extrato exportado do Internet Banking Santander: Data | Histórico | Documento | Valor (R$) | Saldo (R$)."""
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    try:
        todas = list(wb.active.iter_rows(values_only=True))
    finally:
        wb.close()
    linhas, cab, conta = [], None, ""
    for row in todas:
        if cab is None:
            if row and chave(row[0]) == "AGENCIA":
                conta = f"Ag {row[1]} Cc {row[3]}"
            if row and chave(row[0]) == "DATA" and chave(row[1]).startswith("HIST"):
                cab = [chave(c) for c in row]
            continue
        if not row or row[0] in (None, ""):
            continue
        valor = row[3]
        if not isinstance(valor, (int, float)):
            continue
        linhas.append({
            "banco": "Santander", "data": _data_br(row[0]), "descricao": limpar(row[1]),
            "documento": limpar(row[2]), "valor": round(float(valor), 2), "cpf_cnpj": "", "id_banco": "",
        })
    if cab is None:
        raise ValueError(f"{Path(caminho).name}: cabeçalho 'Data | Histórico' não encontrado")
    return {"banco": "Santander", "conta": conta, "lancamentos": _com_ids("Santander", linhas), "saldo_final": None,
            "saldo_data": None}


_DOC = re.compile(r"^\d{2,3}\.\d{3}\.\d{3}([-/]\d{2,4}(-\d{2})?)?$")


def ler_ofx_cora(caminho) -> dict:
    """OFX da Cora. MEMO = "Tipo - Nome - CPF/CNPJ"; a descrição vira "Tipo" + "Nome", igual ao histórico."""
    texto = Path(caminho).read_text(encoding="utf-8", errors="replace")
    linhas = []
    for bloco in re.findall(r"<STMTTRN>(.*?)</STMTTRN>", texto, re.S):
        campo = lambda nome: (re.search(rf"<{nome}>([^<\r\n]*)", bloco) or [None, ""])[1].strip()
        partes = [p.strip() for p in campo("MEMO").split(" - ")]
        doc = partes[-1] if len(partes) > 2 and _DOC.match(partes[-1]) else ""
        nome = " - ".join(partes[1:-1] if doc else partes[1:])
        linhas.append({
            "banco": "Cora", "data": dt.datetime.strptime(campo("DTPOSTED")[:8], "%Y%m%d").date(),
            "descricao": limpar(partes[0] + nome), "documento": campo("FITID"),
            "valor": round(float(campo("TRNAMT")), 2), "cpf_cnpj": doc, "id_banco": campo("FITID"),
        })
    # O OFX vem do mais recente para o mais antigo; a ordem de ocorrência segue a do extrato em ordem de data.
    linhas.sort(key=lambda l: l["data"])
    saldo = re.search(r"<LEDGERBAL>\s*<BALAMT>([^<\r\n]+)(?:</BALAMT>)?\s*(?:<DTASOF>(\d{8}))?", texto)
    conta = re.search(r"<ACCTID>([^<\r\n]+)", texto)
    return {"banco": "Cora", "conta": conta.group(1) if conta else "", "lancamentos": _com_ids("Cora", linhas),
            "saldo_final": float(saldo.group(1)) if saldo else None,
            "saldo_data": dt.datetime.strptime(saldo.group(2), "%Y%m%d").date() if saldo and saldo.group(2) else None}


def _linhas_xls(caminho) -> list[list]:
    import xlrd   # só o RET usa o formato .xls antigo, que o Excel bloqueia por padrão
    with open(os.devnull, "w") as silencio:
        ws = xlrd.open_workbook(caminho, logfile=silencio).sheet_by_index(0)
    return [ws.row_values(i) for i in range(ws.nrows)]


def _eh_ret(linhas) -> bool:
    return bool(linhas) and [chave(c) for c in linhas[0][:2]] == ["PAGO", "VENCIMENTO"]


def _documento(v) -> str:
    # O RET grava parte dos documentos como número: 429686.0 -> "429686".
    return str(int(v)) if isinstance(v, float) and v.is_integer() else limpar(v)


def ler_ret_loterica(caminho, linhas=None) -> dict:
    """Boletos pagos na lotérica, do relatório do RET: Pago | Vencimento | Documento | Par | Duplicata |
    Fornecedor | Compra | Devido R$ | Juros R$ | Desc R$ | Pago R$. Cada boleto vira uma saída da Caixa Loja na
    data Pago, com o fornecedor ("00025 - NOME") como descrição, igual ao histórico."""
    linhas = linhas if linhas is not None else _linhas_xls(caminho)
    if not _eh_ret(linhas):
        raise ValueError(f"{Path(caminho).name}: cabeçalho 'Pago | Vencimento' do RET não encontrado")
    cab = [chave(c) for c in linhas[0]]
    col = {nome: cab.index(nome) for nome in ("PAGO", "DOCUMENTO", "FORNECEDOR", "PAGO R$")}
    saida = []
    for row in linhas[1:]:
        valor = row[col["PAGO R$"]]
        if not isinstance(valor, (int, float)) or not row[col["PAGO"]]:
            continue
        saida.append({
            "banco": "Caixa Loja", "data": _data_br(row[col["PAGO"]]), "descricao": limpar(row[col["FORNECEDOR"]]),
            "documento": _documento(row[col["DOCUMENTO"]]), "valor": -round(float(valor), 2), "cpf_cnpj": "",
            "id_banco": "",
        })
    return {"banco": "Caixa Loja", "conta": "Lotérica (RET)", "lancamentos": _com_ids("Caixa Loja", saida),
            "saldo_final": None, "saldo_data": None}


def ler_extrato(caminho) -> dict:
    sufixo = Path(caminho).suffix.lower()
    if sufixo == ".ofx":
        return ler_ofx_cora(caminho)
    if sufixo == ".xls":
        return ler_ret_loterica(caminho)
    if sufixo == ".xlsx":
        return ler_extrato_santander(caminho)
    raise ValueError(f"Formato não suportado: {sufixo}")
