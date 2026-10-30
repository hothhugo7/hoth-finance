"""Gera as versões do logo usadas na planilha a partir de hoth/assets/hoth_logo_original.webp.

- logo_hoth.png: logo completo (H + HOTH + SOLUTIONS), fundo transparente, para a capa.
- logo_hoth_horizontal.png: H ao lado de HOTH / SOLUTIONS, fundo transparente, para o canto das abas.
O logo é prata sobre fundo escuro: a transparência sai do brilho de cada ponto em relação ao fundo.
"""
from pathlib import Path

from PIL import Image

PASTA = Path(__file__).resolve().parent.parent / "hoth" / "assets"


def transparente(im: Image.Image) -> Image.Image:
    rgb = im.convert("RGB")
    fundo = sum(sum(rgb.getpixel(p)) / 3 for p in [(8, 8), (rgb.width - 8, 8), (8, rgb.height - 8)]) / 3
    alfa = rgb.convert("L").point(lambda v: max(0, min(255, int((v - fundo - 10) * 255 / 70))))
    saida = rgb.copy()
    saida.putalpha(alfa)
    return saida


def recortar(im: Image.Image, margem: int) -> Image.Image:
    caixa = im.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
    x0, y0, x1, y1 = caixa
    return im.crop((max(0, x0 - margem), max(0, y0 - margem), min(im.width, x1 + margem), min(im.height, y1 + margem)))


def main():
    original = Image.open(PASTA / "hoth_logo_original.webp")
    logo = recortar(transparente(original), 24)
    logo.save(PASTA / "logo_hoth.png")

    # Separa a marca (H) do texto: a marca termina na primeira faixa horizontal vazia abaixo dela.
    a = logo.getchannel("A")
    linhas_vazias = [y for y in range(logo.height) if a.crop((0, y, logo.width, y + 1)).getbbox() is None]
    corte = next(y for y in linhas_vazias if y > logo.height * 0.4)
    marca = recortar(logo.crop((0, 0, logo.width, corte)), 6)
    texto = recortar(logo.crop((0, corte, logo.width, logo.height)), 6)
    altura = 200
    marca = marca.resize((int(marca.width * altura / marca.height), altura), Image.LANCZOS)
    texto = texto.resize((int(texto.width * altura * 0.62 / texto.height), int(altura * 0.62)), Image.LANCZOS)
    espaco = 46
    horizontal = Image.new("RGBA", (marca.width + espaco + texto.width, altura), (0, 0, 0, 0))
    horizontal.paste(marca, (0, 0), marca)
    horizontal.paste(texto, (marca.width + espaco, (altura - texto.height) // 2), texto)
    horizontal.save(PASTA / "logo_hoth_horizontal.png")

    # Ícone do programa: a marca (H) sobre um quadrado grafite arredondado.
    from PIL import ImageDraw
    lado = 256
    icone = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    ImageDraw.Draw(icone).rounded_rectangle((0, 0, lado - 1, lado - 1), radius=48, fill=(18, 19, 22, 255))
    m = marca.resize((int(marca.width * 190 / marca.height), 190), Image.LANCZOS)
    icone.alpha_composite(m, ((lado - m.width) // 2, (lado - m.height) // 2))
    icone.save(PASTA / "hoth.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(logo.size, horizontal.size)


if __name__ == "__main__":
    main()
