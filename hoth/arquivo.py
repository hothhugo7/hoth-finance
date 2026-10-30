"""Abertura da planilha Hoth, que pode estar protegida com senha de abertura (arquivo criptografado).

A senha fica em `senha_planilha` no hoth.json. O openpyxl não lê arquivo criptografado: ele é decifrado em
memória (nada é gravado sem senha no disco). O Excel recebe a senha ao abrir e a mantém ao salvar.
"""
import io

import msoffcrypto
import openpyxl

from . import config


class SenhaIncorreta(Exception):
    pass


def senha() -> str:
    return config.carregar().get("senha_planilha") or ""


def protegida(caminho) -> bool:
    with open(caminho, "rb") as f:
        return msoffcrypto.OfficeFile(f).is_encrypted()


def abrir_planilha(caminho, **kw):
    """openpyxl.load_workbook que também abre a planilha com senha."""
    with open(caminho, "rb") as f:
        arquivo = msoffcrypto.OfficeFile(f)
        if not arquivo.is_encrypted():
            return openpyxl.load_workbook(caminho, **kw)
        if not senha():
            raise SenhaIncorreta("A planilha tem senha e o hoth.json não tem 'senha_planilha'.")
        try:
            arquivo.load_key(password=senha())
            claro = io.BytesIO()
            arquivo.decrypt(claro)
        except Exception as e:
            raise SenhaIncorreta(f"Senha da planilha incorreta no hoth.json ({e}).")
    claro.seek(0)
    return openpyxl.load_workbook(claro, **kw)
