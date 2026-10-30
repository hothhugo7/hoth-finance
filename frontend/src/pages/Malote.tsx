import { KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { Save, Trash2 } from "lucide-react";
import { api, CandidatoMalote, dataBR, dinheiro, Malote as MaloteT, valorBR } from "../api";
import { Carregando, DataInput, Metrica, useAviso } from "../components/ui";

type Linha = { valor: number; titulo: CandidatoMalote | null; opcoes: CandidatoMalote[]; observacao: string };

const hojeISO = () => new Date().toISOString().slice(0, 10);

export function Malote() {
  const [envio, setEnvio] = useState<string | null>(hojeISO());
  const [totalFita, setTotalFita] = useState("");
  const [valor, setValor] = useState("");
  const [linhas, setLinhas] = useState<Linha[]>([]);
  const [escolhendo, setEscolhendo] = useState<number | null>(null);   // linha com mais de um título possível
  const [malotes, setMalotes] = useState<MaloteT[]>([]);
  const [aberto, setAberto] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState("");
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
        const opcoes = await api.cpCandidatos(v, envio, escolhidos);
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

  const salvar = async () => {
    if (!envio || !linhas.length) return;
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
          <Save size={16} /> Salvar malote ({linhas.length})
        </button>
      </header>

      {ocupado && <Carregando texto={ocupado} />}

      <div className="cartao">
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
                          <div>{l.titulo.fornecedor} <span className="mini">· venc. {dataBR(l.titulo.vencimento)} · doc. {l.titulo.documento}</span>
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
          <button className="malote-cab" onClick={() => setAberto(aberto === m.id ? null : m.id)}>
            <strong>{dataBR(m.envio)}</strong>
            <span>{m.quantidade} boletos · R$ {dinheiro(m.soma)}</span>
            {m.pendentes
              ? <span className="etiqueta etiqueta-pend">{m.pendentes} sem retorno · R$ {dinheiro(m.valor_pendente)} · {m.dias} dias</span>
              : <span className="etiqueta etiqueta-ok">tudo voltou</span>}
            {m.total_fita != null && Math.abs(m.total_fita - m.soma) > 0.005 && <span className="mini alerta">fita: R$ {dinheiro(m.total_fita)}</span>}
          </button>
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
    </section>
  );
}
