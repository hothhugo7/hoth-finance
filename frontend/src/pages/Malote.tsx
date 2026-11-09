import { KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { Pencil, Save, Trash2 } from "lucide-react";
import { api, CandidatoMalote, dataBR, dinheiro, Malote as MaloteT, valorBR } from "../api";
import { Carregando, DataInput, Metrica, Modal, useAviso } from "../components/ui";

type Linha = { valor: number; titulo: CandidatoMalote | null; opcoes: CandidatoMalote[]; observacao: string; voltou?: boolean };

const hojeISO = () => new Date().toISOString().slice(0, 10);

/** O que muda no malote, em frases, para conferir antes de gravar. */
function mudancasDoMalote(m: MaloteT, envio: string, total: number | null, linhas: Linha[]): string[] {
  const saida: string[] = [];
  if (m.envio !== envio) saida.push(`Data de envio: ${dataBR(m.envio)} → ${dataBR(envio)}`);
  const totalAntes = m.total_fita || null;
  if (totalAntes !== total) saida.push(`Total da fita: ${totalAntes === null ? "vazio" : `R$ ${dinheiro(totalAntes)}`} → ${total === null ? "vazio" : `R$ ${dinheiro(total)}`}`);
  const chave = (titulo: string, valor: number) => `${titulo}|${valor.toFixed(2)}`;
  const restantes = linhas.map((l) => chave(l.titulo?.id ?? "", l.valor));
  for (const v of m.valores) {
    const i = restantes.indexOf(chave(v.titulo, v.valor));
    if (i >= 0) restantes.splice(i, 1);
    else saida.push(`Sai: R$ ${dinheiro(v.valor)} · ${v.fornecedor || "sem título"}${v.voltou ? " (este boleto já voltou)" : ""}`);
  }
  const antes = m.valores.map((v) => chave(v.titulo, v.valor));
  for (const l of linhas) {
    const i = antes.indexOf(chave(l.titulo?.id ?? "", l.valor));
    if (i >= 0) antes.splice(i, 1);
    else saida.push(`Entra: R$ ${dinheiro(l.valor)} · ${l.titulo?.fornecedor ?? "sem título"}`);
  }
  return saida;
}

export function Malote() {
  const [envio, setEnvio] = useState<string | null>(hojeISO());
  const [totalFita, setTotalFita] = useState("");
  const [valor, setValor] = useState("");
  const [linhas, setLinhas] = useState<Linha[]>([]);
  const [escolhendo, setEscolhendo] = useState<number | null>(null);   // linha com mais de um título possível
  const [malotes, setMalotes] = useState<MaloteT[]>([]);
  const [aberto, setAberto] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState("");
  const [editando, setEditando] = useState<MaloteT | null>(null);
  const [revisando, setRevisando] = useState(false);
  const [excluindo, setExcluindo] = useState<MaloteT | null>(null);
  const [conferido, setConferido] = useState(false);
  const campo = useRef<HTMLInputElement>(null);
  const avisar = useAviso();

  const carregar = useCallback(async () => {
    try { setMalotes(await api.cpMalotes()); } catch (e) { avisar("erro", (e as Error).message); }
  }, [avisar]);
  useEffect(() => { carregar(); }, [carregar]);

  // Procura os títulos de vários valores em sequência (digitados um a um ou colados de uma vez).
  const adicionar = async (valores: number[]) => {
    if (!envio) { avisar("erro", "Informe a data de envio do malote."); return; }
    let atuais = [...linhas];
    for (const v of valores) {
      const escolhidos = atuais.map((l) => l.titulo?.id).filter(Boolean) as string[];
      try {
        const opcoes = await api.cpCandidatos(v, envio, escolhidos, editando?.id ?? "");
        const livres = opcoes.filter((o) => !o.outro_malote);
        // Mais de um boleto com o valor: entra o de vencimento mais próximo do envio; dá para trocar.
        atuais = [...atuais, { valor: v, titulo: livres[0] ?? null, opcoes, observacao: "" }];
      } catch (e) {
        avisar("erro", (e as Error).message);
        break;
      }
    }
    setLinhas(atuais);
  };

  const digitar = async (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const v = valorBR(valor);
    if (v === null || v <= 0) { avisar("erro", `Valor inválido: ${valor}`); return; }
    setValor("");
    await adicionar([v]);
  };

  const colar = async (texto: string) => {
    const partes = texto.split(/[\r\n\t;]+/).map((p) => p.trim()).filter(Boolean);
    if (partes.length < 2) return false;
    const vs = partes.map(valorBR);
    if (vs.some((v) => v === null)) { avisar("erro", "Algum valor colado não é número. Cole um valor por linha."); return true; }
    await adicionar(vs as number[]);
    return true;
  };

  const escolher = (i: number, op: CandidatoMalote | null) => {
    setLinhas((ls) => ls.map((l, j) => (j === i ? { ...l, titulo: op } : l)));
    setEscolhendo(null);
    campo.current?.focus();
  };

  const remover = (i: number) => { setLinhas((ls) => ls.filter((_, j) => j !== i)); setEscolhendo(null); };

  const soma = linhas.reduce((s, l) => s + l.valor, 0);
  const total = valorBR(totalFita);
  const diferenca = total === null ? null : Math.round((total - soma) * 100) / 100;
  const semTitulo = linhas.filter((l) => !l.titulo).length;

  const limpar = () => { setLinhas([]); setTotalFita(""); setValor(""); setEscolhendo(null); setEditando(null); setEnvio(hojeISO()); };

  const editar = (m: MaloteT) => {
    setEditando(m);
    setEnvio(m.envio);
    setTotalFita(m.total_fita ? dinheiro(m.total_fita) : "");
    setEscolhendo(null);
    setLinhas(m.valores.map((v) => {
      const titulo = v.titulo ? { id: v.titulo, fornecedor: v.fornecedor, documento: v.documento, parcela: v.parcela, vencimento: v.vencimento ?? "",
                                  valor: v.valor, situacao_texto: v.situacao_texto, outro_malote: "" } : null;
      return { valor: v.valor, titulo, opcoes: titulo ? [titulo] : [], observacao: v.observacao, voltou: v.voltou };
    }));
    campo.current?.closest(".pagina")?.scrollIntoView({ behavior: "smooth" });
    campo.current?.focus();
  };

  const mudancas = editando && envio ? mudancasDoMalote(editando, envio, total, linhas) : [];

  const confirmarEdicao = async () => {
    if (!editando || !envio) return;
    setRevisando(false);
    setOcupado("Gravando as alterações do malote…");
    try {
      const r = await api.cpEditarMalote(editando.id, envio, total, editando.observacao,
        linhas.map((l) => ({ valor: l.valor, titulo: l.titulo?.id ?? "", observacao: l.observacao })));
      avisar("ok", r.detalhe);
      limpar(); setAberto(null);
      await carregar();
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado("");
    }
  };

  const confirmarExclusao = async () => {
    if (!excluindo) return;
    const alvo = excluindo;
    setExcluindo(null);
    setOcupado("Excluindo o malote…");
    try {
      const r = await api.cpExcluirMalote(alvo.id);
      avisar("ok", r.detalhe);
      if (editando?.id === alvo.id) limpar();
      await carregar();
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado("");
    }
  };

  const salvar = async () => {
    if (!envio || !linhas.length) return;
    if (editando) { setConferido(false); setRevisando(true); return; }
    setOcupado("Gravando o malote…");
    try {
      const r = await api.cpSalvarMalote(envio, total, "",
        linhas.map((l) => ({ valor: l.valor, titulo: l.titulo?.id ?? "", observacao: l.observacao })));
      avisar("ok", r.detalhe);
      setLinhas([]); setTotalFita(""); setEscolhendo(null);
      await carregar();
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado("");
    }
  };

  const pendentes = malotes.filter((m) => m.pendentes > 0);

  return (
    <section className="pagina">
      <header className="pagina-cab">
        <div>
          <h1>Malote da lotérica</h1>
          <p className="sub">Digite os valores da fita: a cada Enter o app procura o boleto no Contas a Pagar.</p>
        </div>
        <button className="botao primario" disabled={!linhas.length || !!ocupado} onClick={salvar}>
          <Save size={16} /> {editando ? `Revisar alterações (${linhas.length})` : `Salvar malote (${linhas.length})`}
        </button>
      </header>

      {ocupado && <Carregando texto={ocupado} />}

      <div className={`cartao ${editando ? "malote-editando" : ""}`}>
        {editando && (
          <div className="acoes-linha malote-aviso-edicao">
            <strong>Editando o malote de {dataBR(editando.envio)}</strong>
            <span className="nota">Mude o que precisar e clique em Revisar alterações. Nada é gravado antes de você confirmar.</span>
            <button className="botao" onClick={limpar}>Cancelar edição</button>
          </div>
        )}
        <div className="acoes-linha">
          <label className="nota">Envio <DataInput valor={envio} aoMudar={setEnvio} /></label>
          <label className="nota">Total da fita (opcional)
            <input className="campo campo-valor" value={totalFita} placeholder="19.000,88" onChange={(e) => setTotalFita(e.target.value)} />
          </label>
        </div>
        <input ref={campo} className="campo campo-fita" value={valor} autoFocus inputMode="decimal"
               placeholder="Valor do boleto e Enter (ou cole vários, um por linha)"
               onChange={(e) => setValor(e.target.value)} onKeyDown={digitar}
               onPaste={async (e) => { if (await colar(e.clipboardData.getData("text"))) e.preventDefault(); }} />

        {linhas.length > 0 && (
          <>
            <div className="grade-metricas">
              <Metrica rotulo="Valores digitados" valor={linhas.length} detalhe={`${semTitulo} sem título`} tom={semTitulo ? "alerta" : "ok"} />
              <Metrica rotulo="Soma" valor={dinheiro(soma)} />
              {diferenca !== null && <Metrica rotulo="Diferença para a fita" valor={dinheiro(diferenca)} tom={diferenca === 0 ? "ok" : "alerta"} />}
            </div>
            <table className="tabela tabela-malote">
              <thead><tr><th>#</th><th className="num">Valor</th><th>Boleto no Contas a Pagar</th><th /></tr></thead>
              <tbody>
                {linhas.map((l, i) => {
                  const livres = l.opcoes.filter((o) => !o.outro_malote);
                  return (
                    <tr key={i} className={l.titulo ? "" : "linha-pendente"}>
                      <td className="mini">{i + 1}</td>
                      <td className="num nowrap">{dinheiro(l.valor)}</td>
                      <td>
                        {l.titulo ? (
                          <div>{l.titulo.fornecedor} <span className="mini">· venc. {dataBR(l.titulo.vencimento)} · doc. {l.titulo.documento}{l.voltou ? " · já voltou" : ""}</span>
                            {livres.length > 1 && <button className="link alerta" onClick={() => setEscolhendo(escolhendo === i ? null : i)}>
                              {livres.length} boletos com esse valor — conferir</button>}</div>
                        ) : (
                          <div className="mini alerta">
                            Nenhum boleto em aberto com esse valor{l.opcoes.length ? ` (já está no malote ${l.opcoes[0].outro_malote})` : ""}.
                            <input className="campo campo-desc" placeholder="Observação (opcional)" value={l.observacao}
                                   onChange={(e) => setLinhas((ls) => ls.map((x, j) => (j === i ? { ...x, observacao: e.target.value } : x)))} />
                          </div>
                        )}
                        {escolhendo === i && livres.map((o) => (
                          <button key={o.id} className={`chip ${l.titulo?.id === o.id ? "chip-ativo" : ""}`} onClick={() => escolher(i, o)}>
                            {o.fornecedor} · venc. {dataBR(o.vencimento)} · doc. {o.documento}
                          </button>
                        ))}
                      </td>
                      <td><button className="icone" aria-label="Remover" onClick={() => remover(i)}><Trash2 size={14} /></button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
      </div>

      <h2 className="titulo-secao">Malotes {pendentes.length ? `· ${pendentes.length} com boletos sem retorno` : ""}</h2>
      {malotes.length === 0 && <p className="nota">Nenhum malote registrado.</p>}
      {malotes.map((m) => (
        <div key={m.id} className={`cartao malote ${m.pendentes ? "malote-pendente" : ""}`}>
          <div className="malote-linha">
          <button className="malote-cab" onClick={() => setAberto(aberto === m.id ? null : m.id)}>
            <strong>{dataBR(m.envio)}</strong>
            <span>{m.quantidade} boletos · R$ {dinheiro(m.soma)}</span>
            {m.pendentes
              ? <span className="etiqueta etiqueta-pend">{m.pendentes} sem retorno · R$ {dinheiro(m.valor_pendente)} · {m.dias} dias</span>
              : <span className="etiqueta etiqueta-ok">tudo voltou</span>}
            {m.total_fita != null && Math.abs(m.total_fita - m.soma) > 0.005 && <span className="mini alerta">fita: R$ {dinheiro(m.total_fita)}</span>}
          </button>
          <button className="botao" disabled={!!ocupado || editando?.id === m.id} onClick={() => editar(m)}><Pencil size={14} /> Editar</button>
          <button className="icone" aria-label="Excluir malote" title="Excluir malote" disabled={!!ocupado}
                  onClick={() => { setConferido(false); setExcluindo(m); }}><Trash2 size={14} /></button>
          </div>
          {aberto === m.id && (
            <table className="tabela">
              <tbody>
                {m.valores.map((v, i) => (
                  <tr key={i} className={v.voltou ? "" : "linha-pendente"}>
                    <td className="num nowrap">{dinheiro(v.valor)}</td>
                    <td>{v.fornecedor || <span className="mini alerta">sem título{v.observacao ? ` · ${v.observacao}` : ""}</span>}
                      {v.vencimento && <span className="mini"> · venc. {dataBR(v.vencimento)}</span>}</td>
                    <td className="mini">{v.voltou ? `voltou · pago ${dataBR(v.data_pagamento)}` : v.situacao_texto || "sem retorno"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}

      {revisando && editando && (
        <Modal titulo={`Conferir o malote de ${dataBR(editando.envio)}`} aoFechar={() => setRevisando(false)}
               acoes={<><button className="botao" onClick={() => setRevisando(false)}>Voltar e corrigir</button>
                 <button className="botao primario" disabled={!conferido || !mudancas.length} onClick={confirmarEdicao}>Confirmar e gravar</button></>}>
          {mudancas.length ? <ul className="lista-mudancas">{mudancas.map((t, i) => <li key={i}>{t}</li>)}</ul>
            : <p>Nada mudou neste malote.</p>}
          <p className="nota">Depois da alteração: {linhas.length} boletos · R$ {dinheiro(soma)}. A versão atual vai para o BKP antes de gravar.</p>
          {mudancas.length > 0 && <label className="confirma-malote"><input type="checkbox" checked={conferido} onChange={(e) => setConferido(e.target.checked)} /> Conferi as alterações e estão certas</label>}
        </Modal>
      )}

      {excluindo && (
        <Modal titulo={`Excluir o malote de ${dataBR(excluindo.envio)}?`} aoFechar={() => setExcluindo(null)}
               acoes={<><button className="botao" onClick={() => setExcluindo(null)}>Não excluir</button>
                 <button className="botao primario" disabled={!conferido} onClick={confirmarExclusao}>Excluir malote</button></>}>
          <p>{excluindo.quantidade} boletos · R$ {dinheiro(excluindo.soma)}. Os boletos que ainda não voltaram deixam de aparecer como "no malote" e voltam a ficar em aberto.</p>
          <p className="nota">A versão atual vai para o BKP antes de excluir.</p>
          <label className="confirma-malote"><input type="checkbox" checked={conferido} onChange={(e) => setConferido(e.target.checked)} /> Conferi e quero excluir este malote</label>
        </Modal>
      )}
    </section>
  );
}
