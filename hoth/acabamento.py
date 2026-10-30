"""Acabamento visual feito pelo próprio Excel (COM): logo da Hoth e botões com link.

O openpyxl não desenha formas; por isso, depois de gerar a planilha, ela é aberta no Excel e recebe:
- na Capa: o logo grande e os botões de navegação (formas arredondadas com hiperlink);
- nas abas de relatório: o logo no canto da faixa de título e o botão "Capa".
Tudo leva o prefixo "hoth_" no nome e é refeito do zero a cada vez (pode rodar quantas vezes quiser).
"""
from pathlib import Path

from .modelo import GeradorPlanilha

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO = ASSETS / "logo_hoth.png"
LOGO_HORIZONTAL = ASSETS / "logo_hoth_horizontal.png"
ABAS_RELATORIO = ["DFC", "DRE", "RESUMO", "Faturamento"]

ARREDONDADO = 5          # msoShapeRoundedRectangle
XL_CENTRO = -4108        # xlCenter
GRADIENTE_HORIZONTAL = 1  # msoGradientHorizontal


def _rgb(hexa: str) -> int:
    hexa = hexa.lstrip("#")
    return int(hexa[0:2], 16) + int(hexa[2:4], 16) * 256 + int(hexa[4:6], 16) * 65536


def _limpar(ws):
    for i in range(ws.Shapes.Count, 0, -1):
        if ws.Shapes(i).Name.startswith("hoth_"):
            ws.Shapes(i).Delete()


def _botao(ws, nome, area, titulo, detalhe, destino, primario):
    rng = ws.Range(area)
    margem_x, margem_y = 5, 3
    shp = ws.Shapes.AddShape(ARREDONDADO, rng.Left + margem_x, rng.Top + margem_y,
                             rng.Width - 2 * margem_x, rng.Height - 2 * margem_y)
    shp.Name = f"hoth_btn_{nome}"
    shp.Adjustments.SetItem(1, 0.18)
    if primario:  # prata metálico, como o logo
        shp.Fill.TwoColorGradient(GRADIENTE_HORIZONTAL, 1)
        shp.Fill.ForeColor.RGB = _rgb("F1F3F5")
        shp.Fill.BackColor.RGB = _rgb("9DA3AB")
        shp.Line.ForeColor.RGB = _rgb("D9DDE2")
        cor_titulo, cor_detalhe = "121316", "3A3D43"
    else:
        shp.Fill.Solid()
        shp.Fill.ForeColor.RGB = _rgb("1F2125")
        shp.Line.ForeColor.RGB = _rgb("3A3D43")
        cor_titulo, cor_detalhe = "F1F3F5", "9AA0A8"
    shp.Line.Weight = 0.75
    shp.Shadow.Visible = True
    shp.Shadow.OffsetX, shp.Shadow.OffsetY = 0, 2
    shp.Shadow.Blur = 6
    shp.Shadow.Transparency = 0.55
    shp.Shadow.ForeColor.RGB = 0
    texto = f"{titulo}\n{detalhe}" if detalhe else titulo
    tf = shp.TextFrame
    tf.HorizontalAlignment = XL_CENTRO
    tf.VerticalAlignment = XL_CENTRO
    tf.MarginLeft = tf.MarginRight = 6
    tf.Characters().Text = texto
    tudo = tf.Characters()
    tudo.Font.Name = "Segoe UI"
    t1 = tf.Characters(1, len(titulo))
    t1.Font.Size, t1.Font.Bold, t1.Font.Color = 11, True, _rgb(cor_titulo)
    if detalhe:
        t2 = tf.Characters(len(titulo) + 2, len(detalhe))
        t2.Font.Size, t2.Font.Bold, t2.Font.Color = 8, False, _rgb(cor_detalhe)
    shp.Placement = 2  # move com as células, não muda de tamanho
    ws.Hyperlinks.Add(Anchor=shp, Address="", SubAddress=f"'{destino}'!A1", ScreenTip=f"Abrir {destino}")
    return shp


def _imagem(ws, nome, arquivo, left, top, altura):
    pic = ws.Shapes.AddPicture(str(arquivo), False, True, left, top, -1, -1)
    pic.LockAspectRatio = True
    pic.Height = altura
    pic.Name = nome
    pic.Placement = 3  # não move nem redimensiona com as células
    return pic


def capa(ws):
    _limpar(ws)
    area = ws.Range("B2:M9")
    logo = _imagem(ws, "hoth_logo_capa", LOGO, area.Left, area.Top + 2, area.Height - 4)
    logo.Left = area.Left + (area.Width - logo.Width) / 2
    for secao, linha, botoes in GeradorPlanilha.BOTOES_CAPA:
        for (titulo, detalhe, destino), cols in zip(botoes, GeradorPlanilha.COLUNAS_BOTAO):
            c1, c2 = cols.split(":")
            _botao(ws, f"{destino}", f"{c1}{linha}:{c2}{linha + 2}", titulo, detalhe, destino,
                   primario=secao == "DEMONSTRATIVOS")
    _botao(ws, "Auditoria", "K37:M39", "AUDITORIA", "Histórico de alterações", "Auditoria", primario=False)


def relatorio(ws):
    _limpar(ws)
    linha1 = ws.Range("A1")
    _imagem(ws, "hoth_logo_canto", LOGO_HORIZONTAL, linha1.Left + 8, linha1.Top + 5, linha1.Height - 10)
    # Botão "Capa" na linha do título, no fim da área congelada à esquerda (sempre visível)
    alvo = ws.Range({"DRE": "B1:C1", "Faturamento": "O1"}.get(ws.Name, "B1"))
    shp = _botao(ws, "voltar", alvo.Address, "◂  CAPA", "", "Capa", primario=False)
    shp.TextFrame2.TextRange.Font.Size = 9


def aplicar(wb):
    """Recebe o Workbook do Excel (COM) e refaz todo o acabamento."""
    capa(wb.Worksheets("Capa"))
    nomes = [wb.Worksheets(i).Name for i in range(1, wb.Worksheets.Count + 1)]
    for nome in ABAS_RELATORIO:
        if nome in nomes:
            relatorio(wb.Worksheets(nome))
    wb.Worksheets("Capa").Activate()
    wb.Worksheets("Capa").Range("A1").Select()
