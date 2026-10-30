import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Merge, Pencil, Plus, Trash2, Undo2, Upload } from "lucide-react";
import { api, ContaPlano, GrupoPlano, Plano } from "../api";
import { Carregando, Modal, useAviso } from "../components/ui";

type FormConta = {
  codigo?: string; nome: string; grupo: string; grupo_dre: string; entra_dfc: boolean; entra_dre: boolean;
  dre_manual: boolean; fixo_variavel: string; ativa: boolean; observacao: string;
};
type FormGrupo = { codigo?: string; nome: string; natureza: string; entra_dre: boolean; entra_dfc: boolean; resultado_apos: string; apos: string };

const NATUREZAS = ["Entrada", "Saída", "Movimentação"];

function descreverOp(op: Record<string, unknown>, plano: Plano): string {
  const conta = (c: unknown) => plano.contas.find((x) => x.codigo === c)?.nome ?? String(c);
  switch (op.tipo) {
    case "criar_conta": return `Nova conta ${String(op.nome).toUpperCase()}`;
    case "editar_conta": return `Conta ${op.codigo} alterada${op.nome ? ` (nome: ${String(op.nome).toUpperCase()})` : ""}`;
    case "mesclar": return `Mesclar ${op.de} em ${conta(op.para)}`;
    case "excluir_conta": return `Excluir conta ${op.codigo}`;
    case "criar_grupo": return `Novo grupo ${String(op.nome).toUpperCase()}`;
    case "editar_grupo": return `Grupo ${op.codigo} alterado`;
    case "mover_grupo": return `Grupo ${op.codigo} mudou de posição`;
    case "excluir_grupo": return `Excluir grupo ${op.codigo}`;
    default: return String(op.tipo);
  }
}

export function PlanoContas({ aoMudar }: { aoMudar: () => void }) {
  const [plano, setPlano] = useState<Plano | null>(null);
  const [formConta, setFormConta] = useState<FormConta | null>(null);
  const [formGrupo, setFormGrupo] = useState<FormGrupo | null>(null);
  const [mesclar, setMesclar] = useState<ContaPlano | null>(null);
  const [destino, setDestino] = useState("");
  const [aplicando, setAplicando] = useState(false);
  const [confirmarAplicar, setConfirmarAplicar] = useState(false);
  const [filtro, setFiltro] = useState("");
  const avisar = useAviso();

  useEffect(() => { api.plano().then(setPlano).catch((e) => avisar("erro", e.message)); }, [avisar]);

  const op = async (o: Record<string, unknown>) => {
    try {
      setPlano(await api.operacao(o));
      aoMudar();
      return true;
    } catch (e) {
      avisar("erro", (e as Error).message);
      return false;
    }
  };

  const porGrupo = useMemo(() => {
    const m = new Map<string, ContaPlano[]>();
    plano?.contas.filter((c) => !filtro || c.nome.toUpperCase().includes(filtro.toUpperCase()))
      .forEach((c) => m.set(c.grupo, [...(m.get(c.grupo) ?? []), c]));
    return m;
  }, [plano, filtro]);

  if (!plano) return <Carregando />;
  const nomeGrupo = (c: string) => plano.grupos.find((g) => g.codigo === c)?.nome ?? "";

  const salvarConta = async () => {
    if (!formConta) return;
    const { codigo, ...campos } = formConta;
    const ok = codigo ? await op({ tipo: "editar_conta", codigo, ...campos }) : await op({ tipo: "criar_conta", ...campos });
    if (ok) setFormConta(null);
  };
  const salvarGrupo = async () => {
    if (!formGrupo) return;
    const { codigo, apos, ...campos } = formGrupo;
    const ok = codigo ? await op({ tipo: "editar_grupo", codigo, ...campos }) : await op({ tipo: "criar_grupo", ...campos, apos });
    if (ok) setFormGrupo(null);
  };
  const mover = (g: GrupoPlano, dir: -1 | 1) => {
    const i = plano.grupos.findIndex((x) => x.codigo === g.codigo);
    const lista = plano.grupos.filter((x) => x.codigo !== g.codigo);
    const novaPos = Math.max(0, Math.min(lista.length, i + dir));
    op({ tipo: "mover_grupo", codigo: g.codigo, apos: novaPos === 0 ? "" : lista[novaPos - 1].codigo });
  };
  const aplicar = async () => {
    setConfirmarAplicar(false);
    setAplicando(true);
    try {
      const r = await api.aplicarPlano();
      avisar("ok", `Planilha atualizada: ${r.detalhe}`);
      setPlano(await api.plano());
      aoMudar();
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setAplicando(false);
    }
  };
  const novaConta = (grupo: string): FormConta => ({
    nome: "", grupo, grupo_dre: "", entra_dfc: true, entra_dre: true, dre_manual: false, fixo_variavel: "", ativa: true, observacao: "",
  });

  return (
    <section className="pagina">
      <header className="pagina-cab">
        <div>
          <h1>Plano de contas</h1>
          <p className="sub">As alterações ficam num rascunho. Ao aplicar, a DFC, a DRE e a DRE Manual são refeitas e os lançamentos acompanham renomeações e mesclas.</p>
        </div>
        <div className="acoes-cab">
          <button className="botao" onClick={() => setFormGrupo({ nome: "", natureza: "Saída", entra_dre: true, entra_dfc: true, resultado_apos: "", apos: plano.grupos.at(-1)?.codigo ?? "" })}><Plus size={16} /> Novo grupo</button>
          <button className="botao primario" onClick={() => setFormConta(novaConta(plano.grupos[0]?.codigo ?? ""))}><Plus size={16} /> Nova conta</button>
        </div>
      </header>

      {plano.rascunho.length > 0 && (
        <div className="faixa-rascunho">
          <div>
            <strong>{plano.rascunho.length} alteração{plano.rascunho.length > 1 ? "ões" : ""} no rascunho</strong>
            <ul>{plano.rascunho.map((o, i) => <li key={i}>{descreverOp(o, plano)}</li>)}</ul>
          </div>
          <div className="acoes-cab">
            <button className="botao" disabled={aplicando} onClick={async () => { setPlano(await api.descartar()); aoMudar(); }}><Undo2 size={16} /> Descartar</button>
            <button className="botao primario" disabled={aplicando} onClick={() => setConfirmarAplicar(true)}><Upload size={16} /> {aplicando ? "Aplicando…" : "Aplicar na planilha"}</button>
          </div>
        </div>
      )}
      {aplicando && <Carregando texto="Refazendo a planilha com o plano novo (backup, geração e recálculo no Excel)…" />}

      <div className="filtros"><input className="campo" placeholder="Filtrar contas" value={filtro} onChange={(e) => setFiltro(e.target.value)} /></div>

      {plano.grupos.map((g, i) => (
        <div key={g.codigo} className="cartao grupo">
          <div className="grupo-cab">
            <div>
              <span className="codigo">{g.codigo}</span> <strong>{g.nome}</strong>
              <span className="etiqueta">{g.natureza}</span>
              {!g.entra_dre && <span className="etiqueta">fora da DRE</span>}
              {!g.entra_dfc && <span className="etiqueta">fora da DFC</span>}
              {g.resultado_apos && <span className="mini"> → depois vem {g.resultado_apos}</span>}
            </div>
            <div className="acoes-linha">
              <button className="icone" title="Subir" disabled={i === 0} onClick={() => mover(g, -1)}><ArrowUp size={15} /></button>
              <button className="icone" title="Descer" disabled={i === plano.grupos.length - 1} onClick={() => mover(g, 1)}><ArrowDown size={15} /></button>
              <button className="icone" title="Editar grupo" onClick={() => setFormGrupo({ codigo: g.codigo, nome: g.nome, natureza: g.natureza, entra_dre: g.entra_dre, entra_dfc: g.entra_dfc, resultado_apos: g.resultado_apos, apos: "" })}><Pencil size={15} /></button>
              <button className="icone" title="Nova conta neste grupo" onClick={() => setFormConta(novaConta(g.codigo))}><Plus size={15} /></button>
              <button className="icone" title="Excluir grupo (só vazio)" onClick={() => op({ tipo: "excluir_grupo", codigo: g.codigo })}><Trash2 size={15} /></button>
            </div>
          </div>
          <table className="tabela tabela-plano">
            <tbody>
              {(porGrupo.get(g.codigo) ?? []).map((c) => (
                <tr key={c.codigo} className={c.ativa ? "" : "inativa"}>
                  <td className="codigo">{c.codigo}</td>
                  <td>{c.nome}{c.grupo_dre && <div className="mini">na DRE: {nomeGrupo(c.grupo_dre)}</div>}</td>
                  <td className="etiquetas">
                    {c.entra_dfc && <span className="etiqueta">DFC</span>}
                    {c.entra_dre && <span className={`etiqueta ${c.dre_manual ? "etiqueta-media" : ""}`}>{c.dre_manual ? "DRE digitada" : "DRE"}</span>}
                    {!c.ativa && <span className="etiqueta etiqueta-pend">inativa</span>}
                  </td>
                  <td className="num mini">{c.uso ? `${c.uso.toLocaleString("pt-BR")} usos` : "sem uso"}</td>
                  <td className="acoes-linha">
                    <button className="icone" title="Editar" onClick={() => setFormConta({ codigo: c.codigo, nome: c.nome, grupo: c.grupo, grupo_dre: c.grupo_dre, entra_dfc: c.entra_dfc, entra_dre: c.entra_dre, dre_manual: c.dre_manual, fixo_variavel: c.fixo_variavel, ativa: c.ativa, observacao: c.observacao })}><Pencil size={15} /></button>
                    <button className="icone" title="Mesclar com outra conta" onClick={() => { setMesclar(c); setDestino(""); }}><Merge size={15} /></button>
                    <button className="icone" title={c.uso ? "Tem lançamentos: use mesclar ou desative" : "Excluir"} disabled={c.uso > 0} onClick={() => op({ tipo: "excluir_conta", codigo: c.codigo })}><Trash2 size={15} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {formConta && (
        <Modal titulo={formConta.codigo ? `Editar conta ${formConta.codigo}` : "Nova conta"} aoFechar={() => setFormConta(null)}
               acoes={<><button className="botao" onClick={() => setFormConta(null)}>Cancelar</button><button className="botao primario" onClick={salvarConta}>Guardar no rascunho</button></>}>
          <div className="form">
            <label>Nome<input className="campo" autoFocus value={formConta.nome} onChange={(e) => setFormConta({ ...formConta, nome: e.target.value })} /></label>
            <label>Grupo (DFC)<select className="campo" value={formConta.grupo} onChange={(e) => setFormConta({ ...formConta, grupo: e.target.value })}>
              {plano.grupos.map((g) => <option key={g.codigo} value={g.codigo}>{g.codigo} · {g.nome}</option>)}</select></label>
            <label>Grupo na DRE (se for diferente)<select className="campo" value={formConta.grupo_dre} onChange={(e) => setFormConta({ ...formConta, grupo_dre: e.target.value })}>
              <option value="">O mesmo grupo</option>
              {plano.grupos.map((g) => <option key={g.codigo} value={g.codigo}>{g.codigo} · {g.nome}</option>)}</select></label>
            <label>Fixo / variável<select className="campo" value={formConta.fixo_variavel} onChange={(e) => setFormConta({ ...formConta, fixo_variavel: e.target.value })}>
              <option value="">—</option><option>FIXO</option><option>VARIÁVEL</option></select></label>
            <label className="marcar"><input type="checkbox" checked={formConta.entra_dfc} onChange={(e) => setFormConta({ ...formConta, entra_dfc: e.target.checked })} /> Aparece na DFC</label>
            <label className="marcar"><input type="checkbox" checked={formConta.entra_dre} onChange={(e) => setFormConta({ ...formConta, entra_dre: e.target.checked })} /> Aparece na DRE</label>
            <label className="marcar"><input type="checkbox" disabled={!formConta.entra_dre} checked={formConta.dre_manual} onChange={(e) => setFormConta({ ...formConta, dre_manual: e.target.checked })} /> Valor da DRE é digitado (aba DRE Manual)</label>
            {formConta.codigo && <label className="marcar"><input type="checkbox" checked={formConta.ativa} onChange={(e) => setFormConta({ ...formConta, ativa: e.target.checked })} /> Ativa (aparece nas listas)</label>}
            <label>Observação<input className="campo" value={formConta.observacao} onChange={(e) => setFormConta({ ...formConta, observacao: e.target.value })} /></label>
          </div>
        </Modal>
      )}

      {formGrupo && (
        <Modal titulo={formGrupo.codigo ? `Editar grupo ${formGrupo.codigo}` : "Novo grupo"} aoFechar={() => setFormGrupo(null)}
               acoes={<><button className="botao" onClick={() => setFormGrupo(null)}>Cancelar</button><button className="botao primario" onClick={salvarGrupo}>Guardar no rascunho</button></>}>
          <div className="form">
            <label>Nome<input className="campo" autoFocus value={formGrupo.nome} onChange={(e) => setFormGrupo({ ...formGrupo, nome: e.target.value })} /></label>
            <label>Natureza (totais da DFC)<select className="campo" value={formGrupo.natureza} onChange={(e) => setFormGrupo({ ...formGrupo, natureza: e.target.value })}>
              {NATUREZAS.map((n) => <option key={n}>{n}</option>)}</select></label>
            {!formGrupo.codigo && <label>Posição: depois do grupo<select className="campo" value={formGrupo.apos} onChange={(e) => setFormGrupo({ ...formGrupo, apos: e.target.value })}>
              {plano.grupos.map((g) => <option key={g.codigo} value={g.codigo}>{g.codigo} · {g.nome}</option>)}</select></label>}
            <label>Linha de resultado logo depois (opcional)<input className="campo" placeholder="ex.: EBITDA - LUCRO OPERACIONAL ( = )" value={formGrupo.resultado_apos} onChange={(e) => setFormGrupo({ ...formGrupo, resultado_apos: e.target.value })} /></label>
            <label className="marcar"><input type="checkbox" checked={formGrupo.entra_dre} onChange={(e) => setFormGrupo({ ...formGrupo, entra_dre: e.target.checked })} /> Aparece na DRE</label>
            <label className="marcar"><input type="checkbox" checked={formGrupo.entra_dfc} onChange={(e) => setFormGrupo({ ...formGrupo, entra_dfc: e.target.checked })} /> Aparece na DFC</label>
          </div>
        </Modal>
      )}

      {mesclar && (
        <Modal titulo={`Mesclar ${mesclar.nome}`} aoFechar={() => setMesclar(null)}
               acoes={<><button className="botao" onClick={() => setMesclar(null)}>Cancelar</button>
                 <button className="botao primario" disabled={!destino} onClick={async () => { if (await op({ tipo: "mesclar", de: mesclar.codigo, para: destino })) setMesclar(null); }}>Guardar no rascunho</button></>}>
          <p>Todos os lançamentos, ajustes e valores de <strong>{mesclar.nome}</strong> passam para a conta escolhida, e {mesclar.nome} deixa de existir.</p>
          <select className="campo" value={destino} onChange={(e) => setDestino(e.target.value)}>
            <option value="">Escolha a conta de destino</option>
            {plano.contas.filter((c) => c.codigo !== mesclar.codigo).map((c) => <option key={c.codigo} value={c.codigo}>{c.codigo} · {c.nome}</option>)}
          </select>
        </Modal>
      )}

      {confirmarAplicar && (
        <Modal titulo="Aplicar alterações na planilha" aoFechar={() => setConfirmarAplicar(false)}
               acoes={<><button className="botao" onClick={() => setConfirmarAplicar(false)}>Voltar</button><button className="botao primario" onClick={aplicar}>Aplicar</button></>}>
          <p>A planilha será refeita com o plano novo: {plano.rascunho.length} alterações.</p>
          {Object.keys(plano.renomeacoes).length > 0 && <p>Lançamentos que mudam de conta: {Object.entries(plano.renomeacoes).map(([a, n]) => `${a} → ${n}`).join("; ")}</p>}
          <p className="nota">A versão atual vai para o BKP antes. Formatação feita à mão nas abas DFC, DRE, RESUMO e Faturamento não é mantida (os dados sim). A planilha precisa estar fechada no Excel.</p>
        </Modal>
      )}
    </section>
  );
}
