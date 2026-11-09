"""Move a planilha oficial e as versões (BKP) para outra pasta e aponta o app para lá.

    .venv\\Scripts\\python.exe scripts\\mover_planilha.py "\\\\192.168.0.110\\sistemas\\FECHAMENTO FINANCEIRO\\2026\\Hoth"

1. Confere que a planilha está fechada.
2. Copia a planilha para <destino> e as versões para <destino>\\BKP, conferindo o conteúdo (SHA-256) de cada arquivo.
3. Testa no destino uma gravação completa numa cópia de teste (backup, Excel, troca do arquivo) e apaga o teste.
4. Grava o novo caminho no hoth.json do projeto e do pacote.
5. Só então apaga a planilha e as versões do lugar antigo (para continuar existindo uma planilha só).
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from hoth import config  # noqa: E402
from hoth.gravacao import PlanilhaEmUso, PlanilhaOcupada  # noqa: E402


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def copiar_conferindo(origem: Path, destino: Path):
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origem, destino)
    if sha(origem) != sha(destino):
        raise RuntimeError(f"Cópia diferente do original: {destino}")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    destino = Path(sys.argv[1])
    if not destino.drive:  # ex.: "\servidor" que perdeu uma barra vira "\servidor" = C:\servidor
        print(f"ERRO: caminho sem unidade nem servidor: {destino}. Use C:\\pasta ou \\\\servidor\\pasta.")
        sys.exit(1)
    cfg = config.carregar()
    planilha, bkp = Path(cfg["planilha"]), Path(cfg["pasta_bkp"])
    nova_planilha, novo_bkp = destino / planilha.name, destino / "BKP"
    if nova_planilha.resolve() == planilha.resolve():
        print("A planilha já está nesse lugar.")
        return
    if nova_planilha.exists():
        print(f"ERRO: já existe {nova_planilha}. Nada foi feito.")
        sys.exit(1)
    try:
        PlanilhaEmUso(planilha, bkp).verificar_livre()
    except PlanilhaOcupada as e:
        print(f"ERRO: {e}")
        sys.exit(2)

    print(f"Copiando a planilha para {destino}…")
    copiar_conferindo(planilha, nova_planilha)
    versoes = sorted(bkp.glob("*.xlsx"))
    for v in versoes:
        copiar_conferindo(v, novo_bkp / v.name)
    print(f"{len(versoes)} versões copiadas para {novo_bkp}")

    print("Testando uma gravação no destino (numa cópia de teste)…")
    teste = destino / "~teste_hoth.xlsx"
    teste_bkp = destino / "~teste_hoth_BKP"
    shutil.copy2(nova_planilha, teste)
    try:
        info = PlanilhaEmUso(teste, teste_bkp).gravar_lancamentos(
            [], acao="Teste de gravação", detalhe="teste do novo local", arquivo="")
        assert info["backup"].exists() and teste.exists()
    finally:
        teste.unlink(missing_ok=True)
        shutil.rmtree(teste_bkp, ignore_errors=True)
    print("Gravação no destino: OK")

    arquivos = ([Path(os.environ["HOTH_CONFIG"])] if os.environ.get("HOTH_CONFIG")
                else [RAIZ / "hoth.json", RAIZ / "Pacote" / "Hoth Finance" / "hoth.json"])
    for arquivo in arquivos:
        if arquivo.parent.exists():
            atual = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}
            atual.update(planilha=str(nova_planilha), pasta_bkp=str(novo_bkp),
                         manter_backups=cfg["manter_backups"], pasta_comprovantes=cfg["pasta_comprovantes"])
            arquivo.write_text(json.dumps(atual, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Apontado: {arquivo}")

    planilha.unlink()
    for v in versoes:
        v.unlink()
    print(f"Planilha e versões removidas de {planilha.parent} e {bkp}.")
    print(f"Planilha oficial agora: {nova_planilha}")


if __name__ == "__main__":
    main()
