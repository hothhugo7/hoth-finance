"""Normalização de textos usada para comparar nomes de contas e descrições."""
import hashlib
import re
import unicodedata


def corrigir_acentos(texto: str) -> str:
    """Desfaz acentos corrompidos de UTF-8 lido como Latin-1 (ex.: "MaÃ­ra" -> "Maíra"), comuns em CSV
    aberto direto no Excel."""
    if "Ã" not in texto and "Â" not in texto:
        return texto
    try:
        return texto.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        try:
            return texto.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return texto


def chave(texto) -> str:
    """Forma canônica para comparar nomes: sem acento, maiúsculo, espaços únicos."""
    if texto is None:
        return ""
    s = unicodedata.normalize("NFKD", corrigir_acentos(str(texto))).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def limpar(texto) -> str:
    """Remove espaços nas pontas e espaços repetidos, mantendo acentos."""
    if texto is None:
        return ""
    return re.sub(r"\s+", " ", corrigir_acentos(str(texto))).strip()


def id_lancamento(banco: str, data, valor: float, descricao: str, documento: str, ocorrencia: int) -> str:
    """ID estável de um lançamento.

    `ocorrencia` diferencia lançamentos idênticos no mesmo dia (ex.: dois PIX
    iguais), contando a partir de 1 na ordem em que aparecem no extrato.
    """
    base = "|".join([
        chave(banco), data.isoformat(), f"{valor:.2f}", chave(descricao), chave(documento), str(ocorrencia),
    ])
    return hashlib.sha1(base.encode()).hexdigest()[:16].upper()
