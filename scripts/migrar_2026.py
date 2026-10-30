"""Fases 1 e 2: gera a planilha Hoth com os lançamentos de 2026 da planilha antiga e confere.

A planilha antiga nunca é alterada: ela é copiada para uma pasta temporária e lida de lá.
Se a planilha Hoth já existir, a versão anterior vai para BKP/ antes de ser substituída.

Uso:
    .venv\\Scripts\\python.exe scripts\\migrar_2026.py [--origem CAMINHO] [--sem-excel]
"""
import argparse
import datetime as dt
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from hoth import config  # noqa: E402
from hoth.conferencia import Conferencia  # noqa: E402
from hoth.fechamento_antigo import LeitorFechamento  # noqa: E402
from hoth.gravacao import finalizar_no_excel  # noqa: E402
from hoth.modelo import GeradorPlanilha  # noqa: E402

ORIGEM_PADRAO = r"\\servidor\financeiro\FECHAMENTO FINANCEIRO\2026\01. FECHAMENTO FINANCEIRO EXEMPLO - 2026.xlsx"
SAIDA_PADRAO = Path(config.carregar()["planilha"])


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def fazer_backup(planilha: Path, motivo: str) -> Path | None:
    if not planilha.exists():
        return None
    pasta = Path(config.carregar()["pasta_bkp"])
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{dt.datetime.now():%Y-%m-%d_%H%M%S}_antes_{motivo}_{planilha.name}"
    shutil.copy2(planilha, destino)
    return destino


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origem", default=ORIGEM_PADRAO)
    ap.add_argument("--saida", default=str(SAIDA_PADRAO))
    ap.add_argument("--meses-fechados", type=int, default=9)
    ap.add_argument("--sem-excel", action="store_true", help="não recalcula nem confere (sem Excel instalado)")
    ap.add_argument("--forcar", action="store_true",
                    help="gera de novo mesmo que a planilha já tenha importações (elas se perdem; ficam só no BKP)")
    a = ap.parse_args()
    saida = Path(a.saida)
    if saida.exists() and not a.forcar:
        from hoth.arquivo import abrir_planilha
        wb = abrir_planilha(saida, read_only=True)
        acoes = [r[1] for r in wb["Auditoria"].iter_rows(min_row=2, values_only=True) if r[1]]
        wb.close()
        if any(acao != "Migração inicial" for acao in acoes):
            print("ERRO: a planilha já tem importações ou restaurações registradas na Auditoria. Gerar de novo a partir "
                  "da planilha antiga apagaria esses lançamentos. Use --forcar só se for isso mesmo.")
            sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "fechamento_antigo.xlsx"
        shutil.copy2(a.origem, copia)
        hash_origem = sha256(copia)
        print(f"Lendo cópia da planilha antiga (SHA-256 {hash_origem[:12]}…)")
        migracao = LeitorFechamento(str(copia)).ler()

    agora = dt.datetime.now().replace(microsecond=0)
    for l in migracao.lancamentos:
        l["importado_em"] = agora
    backup = fazer_backup(saida, "migracao")
    auditoria = [[agora, "Migração inicial",
                  f"Lançamentos de {migracao.estrutura.ano} migrados da planilha antiga (SHA-256 {hash_origem})",
                  len(migracao.lancamentos), a.origem, str(backup or "")]]
    print(f"Gerando {saida.name}: {len(migracao.lancamentos)} lançamentos, {len(migracao.estrutura.contas)} contas")
    pos = GeradorPlanilha(migracao.estrutura).gerar(
        saida, lancamentos=migracao.lancamentos, ajustes=migracao.ajustes, orcamento=migracao.orcamento,
        saldos=migracao.saldos_informados, auditoria=auditoria, meses_fechados=a.meses_fechados,
        dre_manual=migracao.dre_manual)
    if backup:
        print(f"Versão anterior guardada em {backup}")
    if a.sem_excel:
        return
    print("Acabamento e recálculo no Excel…")
    finalizar_no_excel(saida)
    conf = Conferencia(saida, migracao, pos, a.meses_fechados)
    conf.comparar()
    relatorio = RAIZ / "Relatorios" / f"Conferencia migracao {migracao.estrutura.ano}.xlsx"
    resumo = conf.salvar(relatorio)
    print(f"Conferência salva em {relatorio}")
    print(resumo)


if __name__ == "__main__":
    main()
