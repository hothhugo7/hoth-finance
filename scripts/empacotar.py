"""Gera o pacote Windows do app Hoth em Pacote/.

    .venv\\Scripts\\python.exe scripts\\empacotar.py [--sem-testes] [--marcador "nome da etapa"]

Passos: testes automáticos, build das telas (npm), executável (PyInstaller) e montagem da pasta
"Pacote/Hoth Solutions" + ZIP datado. A planilha NÃO é copiada: o hoth.json do pacote aponta para a planilha
em uso e para a pasta BKP atuais, para continuar existindo uma planilha só.
"""
import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from hoth import config  # noqa: E402
from hoth.importacao import arquivo_regras_fixas  # noqa: E402

NOME = "Hoth Solutions"
PY = RAIZ / ".venv" / "Scripts" / "python.exe"

LEIA_ME = """HOTH SOLUTIONS — Fechamento Financeiro
=======================================

Abrir: dois cliques em "Hoth Solutions.exe". Fechar a janela encerra o app.

Precisa neste computador:
- Microsoft Excel (desktop) — é ele que grava na planilha;
- Microsoft Edge WebView2 Runtime (já vem no Windows 10/11 atualizado). Sem ele o app abre no navegador.

Planilha e versões:
- O arquivo "hoth.json" diz onde está a planilha em uso, a pasta BKP (versões anteriores) e a pasta dos
  comprovantes do Santander. Para mudar de lugar, feche o app, mova a planilha e ajuste o hoth.json.
- Antes de importar ou alterar, feche a planilha no Excel. Cada gravação guarda a versão anterior no BKP.

Pastas deste pacote:
- Dados\\Extratos: cópia de cada extrato importado;  Dados\\logs: registro de erros do app.
- _internal: arquivos do programa (não mexer).

Ao instalar uma versão nova: substitua a pasta inteira, mas guarde o hoth.json e a pasta Dados.
"""


LEIA_ME_INSTALADOR = """HOTH SOLUTIONS - Instalação
===========================

1. Extraia este ZIP inteiro numa pasta.
2. Dê dois cliques em Instalar.bat.
   - Instala o programa em %LOCALAPPDATA%\\Programs\\Hoth Solutions (não precisa de administrador).
   - Instala o Microsoft Edge WebView2 se faltar (precisa de internet).
   - Avisa se o Microsoft Excel não estiver instalado (ele é necessário para gravar na planilha).
   - Pergunta qual planilha usar: a oficial da rede (padrão) ou a que vem na pasta Planilha deste ZIP.
   - Cria atalhos na Área de Trabalho e no Menu Iniciar.
3. Abra pelo atalho "Hoth Solutions".

Reinstalar/atualizar: rode Instalar.bat de novo (mantém a configuração e os dados).
Desinstalar: Desinstalar.bat (não apaga a planilha nem as versões).
"""


def rodar(cmd, **kw):
    print(">", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-testes", action="store_true")
    ap.add_argument("--marcador", default="", help="nome da etapa: vai no nome do ZIP e no VERSAO.txt")
    a = ap.parse_args()

    if not a.sem_testes:
        rodar([PY, "-m", "pytest", "-q", "tests"], cwd=RAIZ)
    rodar(["npm.cmd", "run", "build"], cwd=RAIZ / "frontend")

    trabalho = RAIZ / "build" / "pyinstaller"
    rodar([PY, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", NOME,
           "--icon", str(RAIZ / "hoth" / "assets" / "hoth.ico"),
           "--add-data", f"{RAIZ / 'hoth' / 'assets'};hoth/assets",
           "--add-data", f"{RAIZ / 'hoth' / 'web' / 'static'};hoth/web/static",
           "--collect-submodules", "uvicorn", "--hidden-import", "win32timezone",
           "--hidden-import", "xlrd",  # leitor do RET (.xls): importado só quando usado
           "--workpath", str(trabalho / "work"), "--distpath", str(trabalho / "dist"),
           "--specpath", str(trabalho), str(RAIZ / "scripts" / "app.py")], cwd=RAIZ)

    pacote = RAIZ / "Pacote" / NOME
    dados_antigos = None
    if (pacote / "Dados").exists():  # preserva Dados e hoth.json de um pacote anterior
        dados_antigos = RAIZ / "Pacote" / "_dados_anteriores"
        shutil.rmtree(dados_antigos, ignore_errors=True)
        shutil.copytree(pacote / "Dados", dados_antigos / "Dados")
        if (pacote / "hoth.json").exists():
            shutil.copy2(pacote / "hoth.json", dados_antigos / "hoth.json")
    shutil.rmtree(pacote, ignore_errors=True)
    shutil.copytree(trabalho / "dist" / NOME, pacote)
    (pacote / "Dados").mkdir(exist_ok=True)
    if dados_antigos:
        shutil.copytree(dados_antigos / "Dados", pacote / "Dados", dirs_exist_ok=True)
        if (dados_antigos / "hoth.json").exists():
            shutil.copy2(dados_antigos / "hoth.json", pacote / "hoth.json")
        shutil.rmtree(dados_antigos, ignore_errors=True)
    if not (pacote / "hoth.json").exists():
        cfg = config.carregar()
        (pacote / "hoth.json").write_text(json.dumps({
            "planilha": cfg["planilha"], "pasta_bkp": cfg["pasta_bkp"], "manter_backups": cfg["manter_backups"],
            "pasta_comprovantes": cfg["pasta_comprovantes"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (pacote / "LEIA-ME.txt").write_text(LEIA_ME, encoding="utf-8")
    # Valores que valem em qualquer computador (o instalador não copia o hoth.json): pasta e senha das faturas.
    cfg = config.carregar()
    padrao = {k: cfg[k] for k in ("pasta_faturas", "senha_fatura") if cfg.get(k)}
    (pacote / "hoth.padrao.json").write_text(json.dumps(padrao, ensure_ascii=False, indent=2), encoding="utf-8")
    base = RAIZ.parent / "Dados" / "classificacoes.sqlite3"   # categorias aprovadas na versão Base do fluxo
    if base.exists():
        shutil.copy2(base, pacote / "cadastro_base.sqlite3")
    versao = f"Hoth Solutions - versão de {dt.datetime.now():%d/%m/%Y %H:%M}\n"
    if a.marcador:
        versao += f"Marcador: {a.marcador}\n"
    (pacote / "VERSAO.txt").write_text(versao, encoding="utf-8")

    # Instalador: programa (sem hoth.json/Dados) + Instalar.bat + cópia da planilha em uso
    inst = RAIZ / "Pacote" / "Instalador"
    shutil.rmtree(inst, ignore_errors=True)
    shutil.copytree(pacote, inst / NOME, ignore=shutil.ignore_patterns("hoth.json", "Dados"))
    for f in (RAIZ / "packaging").iterdir():
        shutil.copy2(f, inst / f.name)
    (inst / "LEIA-ME.txt").write_text(LEIA_ME_INSTALADOR, encoding="utf-8")
    planilha = Path(config.carregar()["planilha"])
    (inst / "Planilha").mkdir()
    shutil.copy2(planilha, inst / "Planilha" / planilha.name)
    regras = arquivo_regras_fixas(planilha)  # acompanham a planilha (ficam ao lado dela)
    if regras.exists():
        shutil.copy2(regras, inst / "Planilha" / regras.name)
    shutil.copy2(pacote / "VERSAO.txt", inst / "VERSAO.txt")
    sufixo = f" - {a.marcador}" if a.marcador else ""
    zip_base = RAIZ / "Pacote" / f"{NOME} - Instalador {dt.date.today():%Y-%m-%d}{sufixo}"
    arquivo = shutil.make_archive(str(zip_base), "zip", root_dir=inst)
    print(f"Pacote pronto: {pacote}")
    print(f"ZIP: {arquivo}")


if __name__ == "__main__":
    main()
