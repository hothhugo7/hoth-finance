"""Edição do Plano de Contas e dos Grupos.

As alterações ficam num rascunho (lista de operações) até você aplicar. Aplicar reconstrói a planilha:
as linhas da DFC, da DRE e da DRE Manual saem do plano, e os lançamentos acompanham renomeações e mesclas.
"""
import copy
import json
from collections import Counter
from pathlib import Path

from .estrutura import ENTRADA, MOVIMENTACAO, SAIDA, Conta, Estrutura, Grupo
from .texto import chave, limpar

NATUREZAS = (ENTRADA, SAIDA, MOVIMENTACAO)


class ErroPlano(ValueError):
    pass


class EditorPlano:
    def __init__(self, estrutura: Estrutura, uso: Counter | None = None):
        """`uso` = quantos lançamentos/ajustes cada conta (nome) tem, para impedir excluir conta com dados."""
        self.base = estrutura
        self.est = copy.deepcopy(estrutura)
        self.uso = uso or Counter()
        self.renomeacoes: dict[str, str] = {}   # nome antigo -> nome novo (inclui mesclas)
        self.operacoes: list[dict] = []

    # ---------------------------------------------------------------- consultas
    def _conta(self, codigo) -> Conta:
        c = next((c for c in self.est.contas if c.codigo == codigo), None)
        if c is None:
            raise ErroPlano(f"Conta {codigo} não existe")
        return c

    def _grupo(self, codigo) -> Grupo:
        g = next((g for g in self.est.grupos if g.codigo == codigo), None)
        if g is None:
            raise ErroPlano(f"Grupo {codigo} não existe")
        return g

    def _nome_livre(self, nome, exceto=None):
        if not nome:
            raise ErroPlano("Informe o nome")
        if any(chave(c.nome) == chave(nome) and c is not exceto for c in self.est.contas):
            raise ErroPlano(f"Já existe uma conta chamada {nome}")

    def _proximo_codigo(self, grupo) -> str:
        usados = [int(c.codigo.split(".")[1]) for c in self.est.contas if c.codigo.startswith(grupo + ".")]
        return f"{grupo}.{(max(usados) + 1) if usados else 1:02d}"

    def _ultima_ordem(self, grupo, dre: bool) -> int:
        ordens = [(c.ordem_dre if dre else c.ordem) for c in self.est.contas
                  if (c.grupo_na_dre if dre else c.grupo) == grupo]
        return (max(ordens) + 1) if ordens else 1

    # ---------------------------------------------------------------- operações
    def aplicar(self, op: dict) -> None:
        tipo = op.get("tipo")
        metodo = getattr(self, f"_op_{tipo}", None)
        if metodo is None:
            raise ErroPlano(f"Operação desconhecida: {tipo}")
        try:
            metodo(**{k: v for k, v in op.items() if k != "tipo"})
        except TypeError as e:
            raise ErroPlano(f"Dados inválidos para {tipo}: {e}")
        self.operacoes.append(op)

    def _op_criar_conta(self, nome, grupo, grupo_dre="", entra_dfc=True, entra_dre=True, dre_manual=False,
                        fixo_variavel="", observacao="", ativa=True):
        nome = limpar(nome).upper()
        self._nome_livre(nome)
        self._grupo(grupo)
        if grupo_dre:
            self._grupo(grupo_dre)
        c = Conta(self._proximo_codigo(grupo), nome, grupo, grupo_dre if grupo_dre != grupo else "",
                  entra_dfc=bool(entra_dfc), entra_dre=bool(entra_dre), dre_manual=bool(dre_manual),
                  fixo_variavel=fixo_variavel or "", observacao=observacao or "", ativa=bool(ativa))
        c.ordem = self._ultima_ordem(grupo, dre=False)
        c.ordem_dre = self._ultima_ordem(c.grupo_na_dre, dre=True)
        self.est.contas.append(c)

    def _op_editar_conta(self, codigo, **campos):
        c = self._conta(codigo)
        if "nome" in campos:
            novo = limpar(campos.pop("nome")).upper()
            if chave(novo) != chave(c.nome):
                self._nome_livre(novo, exceto=c)
                self._registrar_renomeacao(c.nome, novo)
                c.nome = novo
        if "grupo" in campos and campos["grupo"] != c.grupo:
            self._grupo(campos["grupo"])
            c.grupo = campos.pop("grupo")
            c.codigo = self._proximo_codigo(c.grupo)
            c.ordem = self._ultima_ordem(c.grupo, dre=False)
        campos.pop("grupo", None)
        if "grupo_dre" in campos:
            g = campos.pop("grupo_dre") or ""
            if g:
                self._grupo(g)
            c.grupo_dre = "" if g == c.grupo else g
            c.ordem_dre = self._ultima_ordem(c.grupo_na_dre, dre=True)
        for k in ("entra_dfc", "entra_dre", "dre_manual", "ativa"):
            if k in campos:
                setattr(c, k, bool(campos.pop(k)))
        for k in ("fixo_variavel", "observacao"):
            if k in campos:
                setattr(c, k, campos.pop(k) or "")
        if campos:
            raise ErroPlano("Campos desconhecidos: " + ", ".join(campos))

    def _registrar_renomeacao(self, antigo, novo):
        for k, v in list(self.renomeacoes.items()):
            if chave(v) == chave(antigo):
                self.renomeacoes[k] = novo
        self.renomeacoes[antigo] = novo

    def _op_mesclar(self, de, para):
        origem, destino = self._conta(de), self._conta(para)
        if origem is destino:
            raise ErroPlano("Escolha duas contas diferentes")
        self._registrar_renomeacao(origem.nome, destino.nome)
        self.est.contas.remove(origem)

    def _op_excluir_conta(self, codigo):
        c = self._conta(codigo)
        nomes = {chave(c.nome)} | {chave(k) for k, v in self.renomeacoes.items() if chave(v) == chave(c.nome)}
        if sum(q for n, q in self.uso.items() if chave(n) in nomes):
            raise ErroPlano(f"{c.nome} tem lançamentos ou valores. Use mesclar com outra conta ou desative.")
        self.est.contas.remove(c)

    def _op_criar_grupo(self, nome, natureza, entra_dre=True, entra_dfc=True, resultado_apos="", apos=""):
        nome = limpar(nome).upper()
        if natureza not in NATUREZAS:
            raise ErroPlano(f"Natureza deve ser {', '.join(NATUREZAS)}")
        if any(chave(g.nome) == chave(nome) for g in self.est.grupos):
            raise ErroPlano(f"Já existe o grupo {nome}")
        codigo = f"{max(int(g.codigo) for g in self.est.grupos) + 1:02d}"
        g = Grupo(codigo, nome, natureza, bool(entra_dre), bool(entra_dfc), resultado_apos or "")
        pos = next((i + 1 for i, x in enumerate(self.est.grupos) if x.codigo == apos), len(self.est.grupos))
        self.est.grupos.insert(pos, g)

    def _op_editar_grupo(self, codigo, **campos):
        g = self._grupo(codigo)
        if "nome" in campos:
            nome = limpar(campos.pop("nome")).upper()
            if any(chave(x.nome) == chave(nome) and x is not g for x in self.est.grupos):
                raise ErroPlano(f"Já existe o grupo {nome}")
            g.nome = nome
        if "natureza" in campos:
            if campos["natureza"] not in NATUREZAS:
                raise ErroPlano("Natureza inválida")
            g.natureza = campos.pop("natureza")
        for k in ("entra_dre", "entra_dfc", "base_percentual"):
            if k in campos:
                setattr(g, k, bool(campos.pop(k)))
        if "resultado_apos" in campos:
            g.resultado_apos = limpar(campos.pop("resultado_apos")).upper()
        if campos:
            raise ErroPlano("Campos desconhecidos: " + ", ".join(campos))

    def _op_mover_grupo(self, codigo, apos=""):
        g = self._grupo(codigo)
        self.est.grupos.remove(g)
        pos = 0 if not apos else next((i + 1 for i, x in enumerate(self.est.grupos) if x.codigo == apos), None)
        if pos is None:
            raise ErroPlano(f"Grupo {apos} não existe")
        self.est.grupos.insert(pos, g)

    def _op_excluir_grupo(self, codigo):
        g = self._grupo(codigo)
        if any(c.grupo == codigo or c.grupo_dre == codigo for c in self.est.contas):
            raise ErroPlano(f"O grupo {g.nome} ainda tem contas. Mova as contas antes de excluir.")
        self.est.grupos.remove(g)


class Rascunho:
    """Operações pendentes guardadas em disco, para não se perderem se o app fechar."""

    def __init__(self, arquivo):
        self.arquivo = Path(arquivo)

    def operacoes(self) -> list[dict]:
        if not self.arquivo.exists():
            return []
        return json.loads(self.arquivo.read_text(encoding="utf-8"))

    def salvar(self, ops: list[dict]):
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(json.dumps(ops, ensure_ascii=False, indent=1), encoding="utf-8")

    def limpar(self):
        self.arquivo.unlink(missing_ok=True)


def editor_com_rascunho(estrutura, uso, ops) -> EditorPlano:
    ed = EditorPlano(estrutura, uso)
    for op in ops:
        ed.aplicar(op)
    return ed
