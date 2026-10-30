"""Inicia o app Hoth: servidor local em 127.0.0.1 e abre a janela do app.

    python -m hoth.web.servidor [--porta 8765] [--config arquivo.json] [--navegador] [--sem-navegador]

Por padrão abre numa janela própria (Edge WebView2, como um programa). Sem o WebView2, ou com --navegador,
abre no navegador padrão. Fechar a janela encerra o app.
"""
import argparse
import os
import socket
import threading
import time
import webbrowser


def _porta_livre(porta: int) -> int:
    for p in range(porta, porta + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("Nenhuma porta livre entre %d e %d" % (porta, porta + 19))


def _esperar(porta: int, segundos=20):
    fim = time.time() + segundos
    while time.time() < fim:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", porta)) == 0:
                return True
        time.sleep(0.2)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--config", help="hoth.json alternativo (ex.: planilha de teste)")
    ap.add_argument("--navegador", action="store_true", help="abrir no navegador em vez da janela do app")
    ap.add_argument("--sem-navegador", action="store_true", help="só o servidor (testes)")
    a = ap.parse_args()
    import sys
    if sys.stdout is None or sys.stderr is None:  # executável sem console: mensagens vão para um log
        from .. import config
        pasta = config.RAIZ / "Dados" / "logs"
        pasta.mkdir(parents=True, exist_ok=True)
        log = open(pasta / "hoth.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
    if a.config:
        os.environ["HOTH_CONFIG"] = os.path.abspath(a.config)

    import uvicorn

    from .api import app

    porta = _porta_livre(a.porta)
    url = f"http://127.0.0.1:{porta}"
    if a.sem_navegador:
        print(f"Hoth rodando em {url}")
        uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")
        return

    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning"))
    threading.Thread(target=servidor.run, daemon=True).start()
    _esperar(porta)
    if not a.navegador:
        try:
            import webview

            class Janela:  # chamado pelo app (F11) para alternar a tela cheia
                def tela_cheia(self):
                    janela.toggle_fullscreen()

            janela = webview.create_window("Hoth Solutions", url, width=1440, height=900, min_size=(1100, 700),
                                           background_color="#0C0D0F", js_api=Janela())
            webview.start()
            servidor.should_exit = True
            return
        except Exception as e:  # sem WebView2: segue no navegador
            print(f"Janela do app indisponível ({e}); abrindo no navegador.")
    webbrowser.open(url)
    print(f"Hoth rodando em {url} — feche esta janela para encerrar.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        servidor.should_exit = True


if __name__ == "__main__":
    main()
