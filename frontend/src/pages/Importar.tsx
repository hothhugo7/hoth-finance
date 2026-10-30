import { useMemo, useRef, useState } from "react";
import { CheckCircle2, FileUp, Save, Upload, Wand2 } from "lucide-react";
import { api, dataBR, dinheiro, Novo, Previa, ResultadoGravacao } from "../api";
import { Carregando, ContaInput, Metrica, Modal, useAviso } from "../components/ui";

type Filtro = "revisar" | "automaticos" | "todos";

const REGRA: Record<string, string> = {
  exata: "mesma descrição", fornecedor: "fornecedor", tipo: "tipo de operação",
};

function chaveSemelhante(n: Novo) {
  return n.favorecido ? `F:${n.favorecido}` : `D:${n.descricao}`;
}

export function Importar({ contas, aoGravar }: { contas: string[]; aoGravar: () => void }) {
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [escolhas, setEscolhas] = useState<Record<string, string>>({});
  const [filtro, setFiltro] = useState<Filtro>("revisar");
  const [ocupado, setOcupado] = useState("");
  const [confirmar, setConfirmar] = useState(false);
  const [resultado, setResultado] = useState<ResultadoGravacao | null>(null);
  const [arrastando, setArrastando] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);
  const avisar = useAviso();

  const enviar = async (arquivo: File) => {
    setOcupado("Lendo o extrato, os comprovantes e classificando…");
    setResultado(null);
    try {
      const p = await api.previa(arquivo);
      setPrevia(p);
      setEscolhas(Object.fromEntries(p.novos.map((n) => [n.id, n.proposta])));
      setFiltro(p.novos.some((n) => !n.proposta) ? "revisar" : "todos");
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado("");
    }
  };

  const contagem = useMemo(() => {
    if (!previa) return { auto: 0, revisar: 0, semConta: 0 };
    const auto = previa.novos.filter((n) => n.proposta).length;
    return { auto, revisar: previa.novos.length - auto, semConta: previa.novos.filter((n) => !escolhas[n.id]).length };
  }, [previa, escolhas]);

  const linhas = useMemo(() => {
    if (!previa) return [];
    return previa.novos.filter((n) => filtro === "todos" || (filtro === "revisar" ? !n.proposta : !!n.proposta));
  }, [previa, filtro]);

  const semelhantes = (n: Novo) =>
    previa ? previa.novos.filter((x) => x.id !== n.id && !escolhas[x.id] && chaveSemelhante(x) === chaveSemelhante(n)) : [];

  const escolher = (id: string, conta: string) => setEscolhas((e) => ({ ...e, [id]: conta }));

  const aplicarSemelhantes = (n: Novo) => {
    const alvo = semelhantes(n);
    setEscolhas((e) => ({ ...e, ...Object.fromEntries(alvo.map((x) => [x.id, e[n.id]])) }));
    avisar("ok", `${alvo.length} lançamentos parecidos receberam ${escolhas[n.id]}`);
  };

  const gravar = async () => {
    if (!previa) return;
    setConfirmar(false);
    setOcupado("Gravando na planilha (backup, Excel, conferência)…");
    try {
      const r = await api.gravar(previa.token, escolhas);
      setResultado(r);
      setPrevia(null);
      aoGravar();
      avisar("ok", r.detalhe);
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
          <h1>Importar extrato</h1>
          <p className="sub">Santander (.xlsx), Cora (.ofx) ou lotérica do RET (.xls). Nada é gravado até você confirmar.</p>
        </div>
        {previa && (
          <button className="botao primario" disabled={!!ocupado || !previa.novos.length} onClick={() => setConfirmar(true)}>
            <Save size={16} /> Gravar na planilha
          </button>
        )}
      </header>

      {ocupado && <Carregando texto={ocupado} />}

      {!previa && !ocupado && !resultado && (
        <div
          className={`soltar ${arrastando ? "arrastando" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setArrastando(true); }}
          onDragLeave={() => setArrastando(false)}
          onDrop={(e) => {
            e.preventDefault();
            setArrastando(false);
            const f = e.dataTransfer.files[0];
            if (f) enviar(f);
          }}
          onClick={() => entrada.current?.click()}
          role="button"
          tabIndex={0}
        >
          <Upload size={28} />
          <strong>Arraste o extrato aqui ou clique para escolher</strong>
          <span>O arquivo original fica guardado na pasta Dados\Extratos</span>
          <input ref={entrada} type="file" accept=".xlsx,.xls,.ofx" hidden
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) enviar(f); e.target.value = ""; }} />
        </div>
      )}

      {resultado && (
        <div className="cartao cartao-ok">
          <h2><CheckCircle2 size={18} /> Gravado</h2>
          <p>{resultado.detalhe}</p>
          {resultado.duplicados_ignorados > 0 && <p>{resultado.duplicados_ignorados} já estavam na planilha e foram ignorados.</p>}
          {resultado.saldos.map((s) => <p key={s}>Saldo: {s}</p>)}
          {resultado.backup && <p className="nota">Versão anterior guardada em <code>{resultado.backup}</code></p>}
          <button className="botao" onClick={() => setResultado(null)}><FileUp size={16} /> Importar outro extrato</button>
        </div>
      )}

      {previa && (
        <>
          <div className="grade-metricas">
            <Metrica rotulo={`${previa.banco} — ${previa.arquivo}`} valor={previa.lidos} detalhe="lançamentos no extrato" />
            <Metrica rotulo="Já estavam na planilha" valor={previa.ja_existem} detalhe="serão ignorados" />
            <Metrica rotulo="Novos com conta proposta" valor={contagem.auto} tom="ok" />
            <Metrica rotulo="Para revisar" valor={contagem.revisar} tom={contagem.revisar ? "alerta" : "ok"}
                     detalhe={`${contagem.semConta} ainda sem conta`} />
          </div>
          {previa.saldos.map((s) => (
            <p key={s.banco} className="nota">Saldo do extrato: {s.banco} no início de {String(s.mes).padStart(2, "0")}/{s.ano} = R$ {dinheiro(s.saldo)} (vai para Saldos Informados)</p>
          ))}
          {previa.comprovantes_nao_lidos.length > 0 && (
            <p className="nota">Comprovantes que não consegui ler: {previa.comprovantes_nao_lidos.join("; ")}</p>
          )}

          <div className="abas">
            {(["revisar", "automaticos", "todos"] as Filtro[]).map((f) => (
              <button key={f} className={`aba ${filtro === f ? "ativa" : ""}`} onClick={() => setFiltro(f)}>
                {f === "revisar" ? `Para revisar (${contagem.revisar})` : f === "automaticos" ? `Automáticos (${contagem.auto})` : `Todos (${previa.novos.length})`}
              </button>
            ))}
            <button className="botao discreto" onClick={() => setPrevia(null)}>Cancelar</button>
          </div>

          {previa.novos.length === 0 ? (
            <div className="cartao"><p>Tudo o que está neste extrato já está na planilha. Nada a gravar.</p></div>
          ) : (
            <div className="tabela-rolagem">
              <table className="tabela tabela-previa">
                <thead>
                  <tr><th>Data</th><th>Descrição</th><th className="num">Valor</th><th>Conta</th><th>Origem da proposta</th></tr>
                </thead>
                <tbody>
                  {linhas.map((n) => {
                    const sem = semelhantes(n);
                    return (
                      <tr key={n.id} className={escolhas[n.id] ? "" : "linha-pendente"}>
                        <td className="nowrap">{dataBR(n.data)}</td>
                        <td>
                          <div>{n.descricao}</div>
                          {n.favorecido && <div className="mini">Comprovante: <strong>{n.favorecido}</strong> · {n.comprovante}</div>}
                          {n.candidatos.length > 0 && <div className="mini alerta">Dois comprovantes com o mesmo valor: {n.candidatos.join(" | ")}</div>}
                        </td>
                        <td className={`num nowrap ${n.valor < 0 ? "neg" : "pos"}`}>{dinheiro(n.valor)}</td>
                        <td className="col-conta">
                          <ContaInput valor={escolhas[n.id] ?? ""} contas={contas} aoMudar={(v) => escolher(n.id, v)} />
                          {!n.proposta && n.sugestoes.length > 0 && (
                            <div className="sugestoes">
                              {n.sugestoes.map((s) => (
                                <button key={s.conta} className={`chip ${escolhas[n.id] === s.conta ? "chip-ativo" : ""}`}
                                        title={`Sugestão: ${s.motivo}`} aria-label={s.conta}
                                        onClick={() => escolher(n.id, s.conta)}>{s.conta}</button>
                              ))}
                            </div>
                          )}
                          {escolhas[n.id] && sem.length > 0 && (
                            <button className="link" onClick={() => aplicarSemelhantes(n)}>
                              <Wand2 size={12} /> Aplicar a {sem.length} parecido{sem.length > 1 ? "s" : ""} sem conta
                            </button>
                          )}
                        </td>
                        <td className="mini">
                          {n.proposta ? <span className={`etiqueta etiqueta-${n.confianca === "alta" ? "ok" : "media"}`}>{REGRA[n.regra] ?? n.regra} · {n.confianca}</span>
                            : escolhas[n.id] ? <span className="etiqueta etiqueta-ok">revisado</span>
                              : <span className="etiqueta etiqueta-pend">revisar</span>}
                          {escolhas[n.id] && n.proposta && escolhas[n.id] !== n.proposta && <div className="mini">alterada (proposta: {n.proposta})</div>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {confirmar && previa && (
        <Modal titulo="Gravar na planilha" aoFechar={() => setConfirmar(false)}
               acoes={<><button className="botao" onClick={() => setConfirmar(false)}>Voltar</button>
                 <button className="botao primario" onClick={gravar}><Save size={16} /> Gravar</button></>}>
          <p><strong>{previa.novos.length}</strong> lançamentos novos do {previa.banco} serão gravados.</p>
          {contagem.semConta > 0 && <p className="alerta">{contagem.semConta} ficarão sem classificação (aparecem na DFC como "Sem classificação" e podem ser classificados depois em Lançamentos).</p>}
          <p className="nota">Antes de gravar, a versão atual da planilha vai para a pasta BKP. A planilha precisa estar fechada no Excel.</p>
        </Modal>
      )}
    </section>
  );
}
