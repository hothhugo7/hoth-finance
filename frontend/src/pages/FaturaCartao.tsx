import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CreditCard, FileUp, RotateCcw, Save, Wand2 } from "lucide-react";
import { api, dataBR, dinheiro, FaturaArquivo, ListaFaturas, PreviaFatura } from "../api";
import { Carregando, ContaInput, Metrica, Modal, useAviso } from "../components/ui";

const SITUACAO: Record<FaturaArquivo["situacao"], { texto: string; classe: string }> = {
  pronta: { texto: "pronta para abrir", classe: "etiqueta-pend" },
  sem_debito: { texto: "débito ainda não está no extrato", classe: "etiqueta-media" },
  varios_debitos: { texto: "mais de um débito com o valor", classe: "etiqueta-media" },
  aberta: { texto: "aberta pelo app", classe: "etiqueta-ok" },
  aberta_mao: { texto: "já aberta à mão", classe: "etiqueta-ok" },
};

const semParcela = (d: string) => d.replace(/\s*PARC \d\d\/\d\d$/, "");

export function FaturaCartao({ contas, aoGravar }: { contas: string[]; aoGravar: () => void }) {
  const [lista, setLista] = useState<ListaFaturas | null>(null);
  const [previa, setPrevia] = useState<PreviaFatura | null>(null);
  const [arquivo, setArquivo] = useState("");
  const [escolhas, setEscolhas] = useState<Record<string, string>>({});
  const [confirmar, setConfirmar] = useState(false);
  const [desfazer, setDesfazer] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState("");
  const entrada = useRef<HTMLInputElement>(null);
  const avisar = useAviso();

  const carregar = useCallback(async () => {
    setOcupado("Procurando as faturas na pasta…");
    try { setLista(await api.faturas()); } catch (e) { avisar("erro", (e as Error).message); } finally { setOcupado(""); }
  }, [avisar]);
  useEffect(() => { carregar(); }, [carregar]);

  const abrir = async (caminho: string, agrupar = false, arquivoEnviado?: File) => {
    setOcupado("Lendo a fatura e classificando as compras…");
    try {
      const p = arquivoEnviado ? await api.faturaEnviar(arquivoEnviado) : await api.faturaPrevia(caminho, agrupar);
      setPrevia(p);
      setArquivo(caminho);
      setEscolhas(Object.fromEntries(p.itens.map((i) => [i.id, i.proposta])));
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado("");
    }
  };

  const pendentes = previa ? previa.itens.filter((i) => !escolhas[i.id]).length : 0;
  const parecidos = (id: string) => {
    if (!previa) return [];
    const base = previa.itens.find((i) => i.id === id);
    return base ? previa.itens.filter((i) => i.id !== id && !escolhas[i.id] && semParcela(i.descricao) === semParcela(base.descricao)) : [];
  };
  const soma = useMemo(() => (previa ? previa.itens.reduce((s, i) => s + i.valor, 0) : 0), [previa]);

  const gravar = async () => {
    if (!previa) return;
    setConfirmar(false);
    setOcupado("Gravando na planilha (backup, Excel, conferência)…");
    try {
      const r = await api.faturaGravar(previa.token, escolhas);
      avisar("ok", r.detalhe);
      if (r.aviso_fluxo) avisar("erro", r.aviso_fluxo);
      setPrevia(null);
      aoGravar();
      await carregar();
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado("");
    }
  };

  const desfazerFatura = async (id: string) => {
    setDesfazer(null);
    setOcupado("Desfazendo (backup, Excel)…");
    try {
      avisar("ok", (await api.faturaDesfazer(id)).detalhe);
      aoGravar();
      await carregar();
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado("");
    }
  };

  return (
    <section className="pagina">
      <header className="pagina-cab">
        <div>
          <h1>Fatura do cartão</h1>
          <p className="sub">Troca o débito da fatura no Santander pelas compras, cada uma com a sua conta, na data do débito.
            As faturas da pasta aparecem sozinhas; a senha do PDF fica na configuração.</p>
        </div>
        {previa ? (
          <button className="botao primario" disabled={!previa.debito || !!ocupado} onClick={() => setConfirmar(true)}>
            <Save size={16} /> Gravar na planilha
          </button>
        ) : (
          <button className="botao" disabled={!!ocupado} onClick={() => entrada.current?.click()}><FileUp size={16} /> Enviar PDF</button>
        )}
        <input ref={entrada} type="file" accept=".pdf" hidden
               onChange={(e) => { const f = e.target.files?.[0]; if (f) abrir("", false, f); e.target.value = ""; }} />
      </header>

      {ocupado && <Carregando texto={ocupado} />}

      {!previa && lista && !ocupado && (
        <>
          {lista.debitos_sem_pdf.length > 0 && (
            <div className="cartao alerta-cartao">
              <strong>Débitos de fatura no extrato sem o PDF na pasta:</strong>
              {lista.debitos_sem_pdf.map((d) => <div key={d.data} className="mini">{dataBR(d.data)} · R$ {dinheiro(-d.valor)} — salve o PDF em {lista.pasta}</div>)}
            </div>
          )}
          <div className="tabela-rolagem">
            <table className="tabela">
              <thead><tr><th>Vencimento</th><th className="num">Total</th><th>Compras</th><th>Situação</th><th>Arquivo</th><th /></tr></thead>
              <tbody>
                {lista.faturas.map((f) => (
                  <tr key={f.arquivo} className={f.situacao === "pronta" ? "linha-pendente" : ""}>
                    <td className="nowrap">{dataBR(f.vencimento)}</td>
                    <td className="num nowrap">{dinheiro(f.total)}</td>
                    <td>{f.itens}{!f.confere && <span className="mini alerta"> · soma não bate</span>}</td>
                    <td><span className={`etiqueta ${SITUACAO[f.situacao].classe}`}>{SITUACAO[f.situacao].texto}</span>
                      {f.debito && <div className="mini">débito {dataBR(f.debito.data)}</div>}
                      {f.aberta_em && <div className="mini">em {dataBR(f.aberta_em)}</div>}</td>
                    <td className="mini">{f.pasta} · {f.nome}</td>
                    <td>{(f.situacao === "pronta" || f.situacao === "sem_debito") &&
                      <button className="botao" onClick={() => abrir(f.arquivo)}><CreditCard size={15} /> Abrir</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {lista.faturas.length === 0 && <p className="nota vazio">Nenhuma fatura do ano na pasta {lista.pasta}.</p>}
          </div>
          {lista.ignoradas > 0 && <p className="nota">{lista.ignoradas} PDF(s) de outros anos ou de layout antigo foram ignorados.</p>}

          {lista.abertas.length > 0 && (
            <>
              <h2 className="titulo-secao">Abertas pelo app</h2>
              <table className="tabela">
                <tbody>
                  {lista.abertas.map((a) => (
                    <tr key={a.id}>
                      <td>venc. {dataBR(a.vencimento)}</td><td className="num">{dinheiro(a.total)}</td>
                      <td>{a.itens} compras em {dataBR(a.data_debito)}</td>
                      <td><span className={`etiqueta ${a.situacao === "aberta" ? "etiqueta-ok" : ""}`}>{a.situacao}</span></td>
                      <td>{a.situacao === "aberta" && <button className="link" onClick={() => setDesfazer(a.id)}><RotateCcw size={12} /> desfazer</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}

      {previa && !ocupado && (
        <>
          <div className="grade-metricas">
            <Metrica rotulo={`Fatura venc. ${dataBR(previa.vencimento)}`} valor={dinheiro(previa.total)} detalhe={`${previa.cartao} · ${previa.arquivo}`} />
            <Metrica rotulo="Débito no extrato" valor={previa.debito ? dataBR(previa.debito.data) : "não encontrado"}
                     tom={previa.debito ? "ok" : "alerta"} detalhe={previa.debito ? `R$ ${dinheiro(-previa.debito.valor)} · sai e entram as compras` : previa.aviso} />
            <Metrica rotulo="Compras" valor={previa.itens.length} detalhe={`soma R$ ${dinheiro(soma)}`} />
            <Metrica rotulo="Sem conta" valor={pendentes} tom={pendentes ? "alerta" : "ok"} detalhe="entram como Sem classificação" />
          </div>
          <div className="barra-caixa">
            <label className="nota"><input type="checkbox" checked={previa.agrupada} disabled={!arquivo}
                                           onChange={(e) => abrir(arquivo, e.target.checked)} /> Agrupar por estabelecimento</label>
            <button className="botao discreto" onClick={() => setPrevia(null)}>Voltar</button>
          </div>
          <div className="tabela-rolagem">
            <table className="tabela tabela-previa">
              <thead><tr><th>Compra</th><th>Descrição</th><th className="num">Valor</th><th>Conta</th><th>Origem da proposta</th></tr></thead>
              <tbody>
                {previa.itens.map((i) => {
                  const sem = parecidos(i.id);
                  return (
                    <tr key={i.id} className={escolhas[i.id] ? "" : "linha-pendente"}>
                      <td className="nowrap">{dataBR(i.data_compra)}</td>
                      <td>{i.descricao}{previa.agrupada && <div className="mini">{i.texto_fatura}</div>}</td>
                      <td className="num nowrap neg">{dinheiro(-i.valor)}</td>
                      <td className="col-conta">
                        <ContaInput valor={escolhas[i.id] ?? ""} contas={contas} aoMudar={(v) => setEscolhas((e) => ({ ...e, [i.id]: v }))} />
                        {!i.proposta && i.sugestoes.length > 0 && (
                          <div className="sugestoes">{i.sugestoes.map((s) => (
                            <button key={s} className={`chip ${escolhas[i.id] === s ? "chip-ativo" : ""}`} onClick={() => setEscolhas((e) => ({ ...e, [i.id]: s }))}>{s}</button>
                          ))}</div>
                        )}
                        {escolhas[i.id] && sem.length > 0 && (
                          <button className="link" onClick={() => setEscolhas((e) => ({ ...e, ...Object.fromEntries(sem.map((x) => [x.id, e[i.id]])) }))}>
                            <Wand2 size={12} /> Aplicar às outras {sem.length} compras deste estabelecimento
                          </button>
                        )}
                      </td>
                      <td className="mini">{i.proposta ? <span className={`etiqueta etiqueta-${i.confianca === "alta" ? "ok" : "media"}`}>{i.regra} · {i.confianca}</span>
                        : escolhas[i.id] ? <span className="etiqueta etiqueta-ok">revisado</span> : <span className="etiqueta etiqueta-pend">revisar</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {confirmar && previa?.debito && (
        <Modal titulo="Abrir a fatura na planilha" aoFechar={() => setConfirmar(false)}
               acoes={<><button className="botao" onClick={() => setConfirmar(false)}>Voltar</button>
                 <button className="botao primario" onClick={gravar}><Save size={16} /> Gravar</button></>}>
          <p>O débito de <strong>{dataBR(previa.debito.data)}</strong> (R$ {dinheiro(-previa.debito.valor)}) sai e entram <strong>{previa.itens.length}</strong> compras na mesma data.</p>
          {pendentes > 0 && <p className="alerta">{pendentes} compra(s) sem conta entram como Sem classificação.</p>}
          <p className="nota">Antes, a versão atual da planilha vai para o BKP. A planilha precisa estar fechada no Excel. Dá para desfazer depois.</p>
        </Modal>
      )}
      {desfazer && (
        <Modal titulo="Desfazer a fatura" aoFechar={() => setDesfazer(null)}
               acoes={<><button className="botao" onClick={() => setDesfazer(null)}>Voltar</button>
                 <button className="botao primario" onClick={() => desfazerFatura(desfazer)}><RotateCcw size={16} /> Desfazer</button></>}>
          <p>As compras saem e volta a linha única do débito, como estava antes. Fica registrado na Auditoria, com backup.</p>
        </Modal>
      )}
    </section>
  );
}
