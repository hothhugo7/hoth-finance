"""Gravação na planilha em uso (sempre o mesmo arquivo), com backup da versão anterior.

Passos de cada gravação:
1. Confere se a planilha está fechada (ninguém com ela aberta no Excel).
2. Copia a versão atual para a pasta BKP.
3. Trabalha numa cópia temporária ao lado da planilha, pelo próprio Excel (preserva tudo o que
   houver no arquivo: fórmulas, formatação, gráficos), confere de novo os duplicados e grava.
4. Confere a cópia gravada e só então troca a planilha pela cópia.
Se algo falhar no meio, a planilha original não é tocada.
"""
import datetime as dt
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

from .arquivo import abrir_planilha, senha

from .texto import chave

COLUNAS_VALOR = ["ID", "Banco", "Data", "Descrição", "Documento", "Valor", "Conta", "Origem", "Referência",
                 "Observação", "Importado em"]


class PlanilhaOcupada(Exception):
    pass


@contextmanager
def excel():
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    app = win32com.client.DispatchEx("Excel.Application")  # instância própria: não mexe no Excel do usuário
    app.Visible = False
    app.DisplayAlerts = False
    try:
        yield app
    finally:
        try:
            for wb in list(app.Workbooks):
                wb.Close(False)
        finally:
            app.Quit()
            pythoncom.CoUninitialize()


def _substituir(origem: Path, destino: Path, tentativas: int = 20):
    """os.replace com novas tentativas: o Excel às vezes demora alguns segundos para soltar o arquivo."""
    for i in range(tentativas):
        try:
            os.replace(origem, destino)
            return
        except PermissionError:
            if i == tentativas - 1:
                raise
            time.sleep(0.5)


def _abrir(app, caminho):
    """Abre no Excel passando a senha de abertura (ignorada se o arquivo não tiver senha)."""
    if senha():
        return app.Workbooks.Open(Filename=str(caminho), Password=senha())
    return app.Workbooks.Open(str(caminho))


def _salvar(wb):
    """Salva mantendo (ou aplicando) a senha de abertura configurada."""
    if senha():
        wb.Password = senha()
    wb.Save()


def finalizar_no_excel(caminho):
    """Abre a planilha recém-gerada no Excel: logo, botões (acabamento), recálculo e salva."""
    from . import acabamento

    with excel() as app:
        wb = _abrir(app, caminho)
        acabamento.aplicar(wb)
        app.CalculateFull()
        _salvar(wb)
        wb.Close(False)


def _colunas(lo) -> dict:
    return {lo.ListColumns(i).Name: i for i in range(1, lo.ListColumns.Count + 1)}


def _bloco(ws, linha, coluna, valores):
    if valores:
        ws.Range(ws.Cells(linha, coluna), ws.Cells(linha + len(valores) - 1, coluna)).Value = [(v,) for v in valores]


_EPOCA_EXCEL = dt.datetime(1899, 12, 30)


def _excel_data(v):
    """Data/hora como número de série do Excel. Passar datetime pelo COM desloca o horário pelo fuso."""
    if isinstance(v, dt.datetime):
        return (v - _EPOCA_EXCEL).total_seconds() / 86400
    if isinstance(v, dt.date):
        return float((v - _EPOCA_EXCEL.date()).days)
    return v


class PlanilhaEmUso:
    def __init__(self, caminho, pasta_bkp, manter_backups: int = 60):
        self.caminho = Path(caminho)
        self.pasta_bkp = Path(pasta_bkp)
        self.manter = manter_backups

    # ----------------------------------------------------------------- checagens
    def verificar_livre(self):
        if not self.caminho.exists():
            raise FileNotFoundError(self.caminho)
        trava = self.caminho.with_name("~$" + self.caminho.name)
        try:
            with open(self.caminho, "r+b"):
                pass
        except PermissionError:
            raise PlanilhaOcupada(f"A planilha está aberta no Excel (feche e tente de novo): {self.caminho.name}")
        if trava.exists():
            raise PlanilhaOcupada(f"A planilha parece aberta no Excel (arquivo {trava.name}). Feche e tente de novo.")

    # ------------------------------------------------------------------- backups
    def backup(self, motivo: str) -> Path:
        self.pasta_bkp.mkdir(parents=True, exist_ok=True)
        motivo = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in motivo).strip()[:60]
        destino = self.pasta_bkp / f"{dt.datetime.now():%Y-%m-%d_%H%M%S}_antes_{motivo}.xlsx"
        shutil.copy2(self.caminho, destino)
        return destino

    def listar_backups(self) -> list[Path]:
        return sorted(self.pasta_bkp.glob("*_antes_*.xlsx"), reverse=True)

    def _limpar_backups(self):
        for antigo in self.listar_backups()[self.manter:]:
            antigo.unlink()

    # ------------------------------------------------------------------ leitura
    def ids_existentes(self) -> set:
        wb = abrir_planilha(self.caminho, read_only=True)
        try:
            return {r[0] for r in wb["Lançamentos"].iter_rows(min_row=2, max_col=1, values_only=True) if r[0]}
        finally:
            wb.close()

    def contas(self) -> list[str]:
        wb = abrir_planilha(self.caminho, read_only=True)
        try:
            return [r[1] for r in wb["Plano de Contas"].iter_rows(min_row=2, max_col=2, values_only=True) if r[1]]
        finally:
            wb.close()

    # ------------------------------------------------------------------ gravação
    def _trocar(self, funcao, motivo: str) -> tuple[Path, object]:
        """Roda `funcao(workbook do Excel, caminho do backup)` numa cópia temporária e troca a planilha no fim."""
        self.verificar_livre()
        bkp = self.backup(motivo)
        tmp = self.caminho.with_name(f"~hoth_gravando_{self.caminho.name}")
        shutil.copy2(self.caminho, tmp)
        try:
            with excel() as app:
                wb = _abrir(app, tmp)
                resultado = funcao(wb, bkp)
                app.CalculateFull()
                _salvar(wb)
                wb.Close(False)
            self.verificar_livre()
            _substituir(tmp, self.caminho)
        except BaseException:
            bkp.unlink(missing_ok=True)  # nada mudou: o backup seria só uma cópia igual à planilha
            raise
        finally:
            if tmp.exists():
                tmp.unlink()
        self._limpar_backups()
        return bkp, resultado

    def gravar_lancamentos(self, novos: list[dict], *, acao: str, detalhe: str, arquivo: str,
                           saldos: list[dict] = ()) -> dict:
        """Acrescenta `novos` (dicts com as chaves de COLUNAS_VALOR em minúsculas sem acento) ao fim de tbLanc."""
        info = {}
        motivo = f"importacao {acao}"

        def gravar(wb, bkp):
            ws = wb.Worksheets("Lançamentos")
            n = ws.ListObjects("tbLanc").ListRows.Count
            info["gravados"], info["duplicados_ignorados"] = self._acrescentar(ws, novos)
            info["saldos"] = self._gravar_saldos(wb, saldos)
            self._auditar(wb, acao, detalhe + (f" ({info['duplicados_ignorados']} já existiam)"
                                               if info["duplicados_ignorados"] else ""),
                          info["gravados"], arquivo, str(bkp))
            return n

        bkp, n_antes = self._trocar(gravar, motivo)
        info["backup"] = bkp
        info["linhas_antes"] = n_antes
        return info

    @staticmethod
    def _acrescentar(ws, novos: list[dict]) -> tuple[int, int]:
        """Acrescenta ao fim de tbLanc os lançamentos cujo ID ainda não existe. Devolve (gravados, duplicados)."""
        lo = ws.ListObjects("tbLanc")
        cols = _colunas(lo)
        n = lo.ListRows.Count
        existentes = set()
        if n:
            existentes = {r[0] for r in lo.ListColumns("ID").DataBodyRange.Value if r[0]}
        entrar = [l for l in novos if l["id"] not in existentes]
        if entrar:
            primeira = lo.HeaderRowRange.Row + n + 1
            lo.Resize(ws.Range(lo.Range.Cells(1, 1), lo.Range.Cells(n + 1 + len(entrar), lo.ListColumns.Count)))
            agora = dt.datetime.now().replace(microsecond=0)
            campos = {"ID": "id", "Banco": "banco", "Data": "data", "Descrição": "descricao",
                      "Documento": "documento", "Valor": "valor", "Conta": "conta", "Origem": "origem",
                      "Referência": "referencia", "Observação": "observacao"}
            for cab in ("ID", "Documento"):  # texto: um ID como "1234E567" viraria número no Excel
                ws.Range(ws.Cells(primeira, cols[cab]), ws.Cells(primeira + len(entrar) - 1, cols[cab])
                         ).NumberFormat = "@"
            for cab, campo in campos.items():
                if campo == "valor":
                    valores = [l["valor"] for l in entrar]
                elif cab in ("ID", "Documento"):
                    valores = [str(l.get(campo) or "") or None for l in entrar]
                else:
                    valores = [_excel_data(l.get(campo) or None) for l in entrar]
                _bloco(ws, primeira, cols[cab], valores)
            _bloco(ws, primeira, cols["Importado em"], [_excel_data(agora)] * len(entrar))
            ultima = primeira + len(entrar) - 1
            ws.Range(ws.Cells(primeira, cols["Data"]), ws.Cells(ultima, cols["Data"])).NumberFormat = "dd/mm/yyyy"
            ws.Range(ws.Cells(primeira, cols["Importado em"]),
                     ws.Cells(ultima, cols["Importado em"])).NumberFormat = "dd/mm/yyyy hh:mm"
        return len(entrar), len(novos) - len(entrar)

    def substituir_lancamentos(self, remover: list[str], novos: list[dict], *, acao: str, detalhe: str,
                               arquivo: str = "") -> dict:
        """Troca lançamentos numa gravação só: remove as linhas com os IDs de `remover` e acrescenta `novos`.
        Usado para abrir a fatura do cartão (sai o débito, entram as compras) e para desfazer. Se algum ID de
        `remover` não estiver na planilha, nada é gravado."""
        info = {}

        def trocar(wb, bkp):
            ws = wb.Worksheets("Lançamentos")
            lo = ws.ListObjects("tbLanc")
            ids = [str(r[0]) for r in lo.ListColumns("ID").DataBodyRange.Value] if lo.ListRows.Count else []
            alvo = set(remover)
            posicoes = [i + 1 for i, v in enumerate(ids) if v in alvo]
            faltam = alvo - {ids[p - 1] for p in posicoes}
            if faltam:
                raise ValueError("Lançamento não encontrado na planilha (já foi alterado?): " + ", ".join(sorted(faltam)))
            for p in sorted(posicoes, reverse=True):   # de baixo para cima, para as posições não mudarem
                lo.ListRows(p).Delete()
            info["removidos"] = len(posicoes)
            info["gravados"], info["duplicados_ignorados"] = self._acrescentar(ws, novos)
            self._auditar(wb, acao, detalhe, info["gravados"], arquivo, str(bkp))

        bkp, _ = self._trocar(trocar, acao)
        info["backup"] = bkp
        return info

    def _gravar_saldos(self, wb, saldos) -> list[str]:
        if not saldos:
            return []
        lo = wb.Worksheets("Saldos Informados").ListObjects("tbSaldos")
        atuais = {}
        if lo.ListRows.Count:
            for b, a, m, s in lo.DataBodyRange.Value:
                atuais[(chave(b), int(a or 0), int(m or 0))] = s
        msgs = []
        for s in saldos:
            k = (chave(s["banco"]), s["ano"], s["mes"])
            if k in atuais:
                if abs((atuais[k] or 0) - s["saldo"]) > 0.005:
                    msgs.append(f"{s['banco']} {s['mes']:02d}/{s['ano']}: já havia saldo informado {atuais[k]:.2f}; "
                                f"o extrato diz {s['saldo']:.2f} (não alterado)")
                continue
            lo.ListRows.Add().Range.Value = ((s["banco"], s["ano"], s["mes"], s["saldo"]),)
            msgs.append(f"{s['banco']} {s['mes']:02d}/{s['ano']}: saldo inicial informado {s['saldo']:.2f}")
        return msgs

    def _auditar(self, wb, acao, detalhe, linhas, arquivo, backup):
        lo = wb.Worksheets("Auditoria").ListObjects("tbAuditoria")
        linha = lo.ListRows.Add()
        linha.Range.Value = ((_excel_data(dt.datetime.now().replace(microsecond=0)), acao, detalhe, linhas, arquivo,
                              backup),)
        linha.Range.Cells(1, 1).NumberFormat = "dd/mm/yyyy hh:mm"

    def restaurar(self, backup) -> Path:
        """Volta a planilha para a versão `backup`. A versão atual também vai para o BKP antes."""
        backup = Path(backup)
        if not backup.exists():
            raise FileNotFoundError(backup)
        self.verificar_livre()
        bkp_atual = self.backup("restauracao")
        tmp = self.caminho.with_name(f"~hoth_gravando_{self.caminho.name}")
        shutil.copy2(backup, tmp)
        try:
            with excel() as app:
                wb = _abrir(app, tmp)
                self._auditar(wb, "Restauração", f"Planilha voltou para a versão {backup.name}", 0, str(backup),
                              str(bkp_atual))
                _salvar(wb)
                wb.Close(False)
            _substituir(tmp, self.caminho)
        finally:
            if tmp.exists():
                tmp.unlink()
        self._limpar_backups()
        return bkp_atual

    # --------------------------------------------------------- reclassificação
    def reclassificar(self, ids: list[str], conta: str, origem: str) -> dict:
        """Troca a conta de lançamentos já gravados (identificados pelo ID)."""
        alvo = set(ids)
        info = {}

        def trocar(wb, bkp):
            ws = wb.Worksheets("Lançamentos")
            lo = ws.ListObjects("tbLanc")
            cols = _colunas(lo)
            primeira = lo.HeaderRowRange.Row + 1
            valores = lo.ListColumns("ID").DataBodyRange.Value if lo.ListRows.Count else ()
            linhas = [primeira + i for i, r in enumerate(valores) if str(r[0]) in alvo]
            for r in linhas:
                ws.Cells(r, cols["Conta"]).Value = conta or None
                ws.Cells(r, cols["Origem"]).Value = origem
            info["alterados"] = len(linhas)
            self._auditar(wb, "Reclassificação", f"{len(linhas)} lançamentos para {conta or '(sem classificação)'}",
                          len(linhas), "", str(bkp))

        bkp, _ = self._trocar(trocar, "reclassificacao")
        info["backup"] = bkp
        return info

    # ------------------------------------------------------------ reconstrução
    def reconstruir(self, conteudo, acao: str, detalhe: str, motivo: str = "alteracao do plano") -> Path:
        """Gera de novo a planilha inteira a partir de `conteudo` (dados atuais + plano alterado).

        Usado quando o Plano de Contas ou os Grupos mudam: as linhas da DFC, da DRE e da DRE Manual dependem deles.
        Os dados (lançamentos, ajustes, orçamento, saldos, auditoria) são preservados.
        """
        from .modelo import GeradorPlanilha

        if conteudo.abas_extras:
            raise ValueError("A planilha tem abas que não são do Hoth (" + ", ".join(conteudo.abas_extras) + "). "
                             "Mova essas abas para outro arquivo antes de aplicar alterações no plano.")
        self.verificar_livre()
        bkp = self.backup(motivo)
        tmp = self.caminho.with_name(f"~hoth_gravando_{self.caminho.name}")
        try:
            auditoria = conteudo.auditoria + [[dt.datetime.now().replace(microsecond=0), acao, detalhe, 0, "",
                                               str(bkp)]]
            GeradorPlanilha(conteudo.estrutura).gerar(
                tmp, lancamentos=conteudo.lancamentos, ajustes=conteudo.ajustes, orcamento=conteudo.orcamento,
                saldos=conteudo.saldos, auditoria=auditoria, meses_fechados=conteudo.meses_fechados,
                dre_manual=conteudo.dre_manual)
            finalizar_no_excel(tmp)
            self.verificar_livre()
            _substituir(tmp, self.caminho)
        except BaseException:
            bkp.unlink(missing_ok=True)
            raise
        finally:
            if tmp.exists():
                tmp.unlink()
        self._limpar_backups()
        return bkp

