import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, ClipboardPaste, Save } from "lucide-react";
import { api, dataBR, dinheiro, LinhaCaixa, UltimoCaixa } from "../api";
import { Carregando, ContaInput, DataInput, Metrica, Modal, useAviso } from "../components/ui";

type Resultado = { gravados: number; duplicados_ignorados: number; detalhe: string; backup: string | null };

function inicioMesAnterior() {
  const h = new Date();
  const d = new Date(h.getFullYear(), h.getMonth() - 1, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function lerDesde() {
  try {
    return localStorage.getItem("caixa-desde") || inicioMesAnterior();
  } catch {
    return inicioMesAnterior();
  }
}

function situacao(l: LinhaCaixa) {
  if (l.fora_periodo) return { texto: "antes do período", classe: "etiqueta-media" };
  if (l.ja_existe) return { texto: "já está na Hoth", classe: "etiqueta-media" };
  if (l.loterica) return { texto: "lotérica (vem do RET)", classe: "etiqueta-media" };
  if (l.correcao_de) return { texto: "possível correção", classe: "etiqueta-pend" };
  if (l.avisos.length) return { texto: "corrigir", classe: "etiqueta-pend" };
  if (!l.conta) return { texto: "sem conta", classe: "etiqueta-pend" };
  return { texto: "ok", classe: "etiqueta-ok" };
}

export function ColarCaixa({ contas, aoGravar }: { contas: string[]; aoGravar: () => void }) {
  const [texto, setTexto] = useState("");
  const [linhas, setLinhas] = useState<LinhaCaixa[] | null>(null);
  const [ocupado, setOcupado] = useState("");
  const [confirmar, setConfirmar] = useState(false);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [desde, setDesde] = useState(lerDesde);
  const [ultimo, setUltimo] = useState<UltimoCaixa | null>(null);
  useEffect(() => { api.caixaUltimo().then(setUltimo).catch(() => setUltimo(null)); }, [resultado]);
  const [todas, setTodas] = useState(false);
  const avisar = useAviso();

  const ler = async (t: string, inicio = desde) => {
    if (!t.trim()) return;
    setTexto(t);
    setOcupado("Lendo as linhas coladas…");
    setResultado(null);
    try {
      setLinhas((await api.caixaInterpretar(t, inicio)).linhas);
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado("");
    }
  };

  // Ctrl+V em qualquer lugar da tela (fora dos campos) lê a nova seleção.
  useEffect(() => {
    const colar = (e: ClipboardEvent) => {
      const alvo = e.target as HTMLElement;
      if (alvo.closest("input, textarea") || ocupado) return;
      const t = e.clipboardData?.getData("text") ?? "";
      if (t.trim()) {
        e.preventDefault();
        ler(t);
      }
    };
    document.addEventListener("paste", colar);
    return () => document.removeEventListener("paste", colar);
  });

  const mudarDesde = (v: string) => {
    setDesde(v);
    try {
      localStorage.setItem("caixa-desde", v);
    } catch {
      /* sem armazenamento: vale só nesta sessão */
    }
    if (linhas && v) ler(texto, v);
  };

  const mudar = (i: number, campos: Partial<LinhaCaixa>) =>
    setLinhas((ls) => ls && ls.map((l, j) => (j === i ? { ...l, ...campos } : l)));

  const resumo = useMemo(() => {
    const sel = (linhas ?? []).filter((l) => l.incluir);
    return {
      total: (linhas ?? []).filter((l) => !l.fora_periodo).length, marcadas: sel.length,
      entradas: sel.reduce((s, l) => s + Math.max(l.valor, 0), 0),
      saidas: sel.reduce((s, l) => s + Math.min(l.valor, 0), 0),
      semConta: sel.filter((l) => !l.conta).length,
      jaExistem: (linhas ?? []).filter((l) => l.ja_existe && !l.fora_periodo).length,
      fora: (linhas ?? []).filter((l) => l.fora_periodo).length,
      correcoes: (linhas ?? []).filter((l) => l.correcao_de && !l.incluir).length,
    };
  }, [linhas]);

  const gravar = async () => {
    if (!linhas) return;
    setConfirmar(false);
    setOcupado("Gravando na planilha (backup, Excel, conferência)…");
    try {
      const r = await api.caixaGravar(linhas);
      setResultado(r);
      setLinhas(null);
      setTexto("");
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
          <h1>Colar Caixa Loja</h1>
          <p className="sub">Copie as linhas do CONTROLE DE CAIXA (de DATA até SAÍDA) e cole aqui. Corrija o que precisar antes de gravar.</p>
        </div>
        {linhas && (
          <button className="botao primario" disabled={!!ocupado || !resumo.marcadas} onClick={() => setConfirmar(true)}>
            <Save size={16} /> Gravar {resumo.marcadas} na planilha
          </button>
        )}
      </header>

      {ocupado && <Carregando texto={ocupado} />}

      {resultado && (
        <div className="cartao cartao-ok">
          <h2><CheckCircle2 size={18} /> Gravado</h2>
          <p>{resultado.detalhe}</p>
          {resultado.duplicados_ignorados > 0 && <p>{resultado.duplicados_ignorados} já estavam na planilha e foram ignorados.</p>}
          {resultado.backup && <p className="nota">Versão anterior guardada em <code>{resultado.backup}</code></p>}
        </div>
      )}

      {!linhas && !ocupado && ultimo?.ultima_data && (
        <div className="cartao cartao-ultimo">
          <div className="acoes-linha">
            <strong>Última linha do CONTROLE que já está na Hoth</strong>
            {ultimo.ultima_colagem && <span className="nota">última colagem em {dataBR(ultimo.ultima_colagem)}</span>}
          </div>
          <table className="tabela tabela-ultimos">
            <tbody>
              {ultimo.linhas.map((l, i) => (
                <tr key={i}><td className="nowrap">{dataBR(l.data)}</td><td>{l.descricao}</td>
                  <td className={`num nowrap ${l.valor < 0 ? "neg" : "pos"}`}>{dinheiro(l.valor)}</td><td className="mini">{l.conta}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="nota">Ache esta linha no CONTROLE DE CAIXA e copie todas as que estão abaixo dela.</p>
        </div>
      )}

      {!linhas && !ocupado && (
        <div className="cartao">
          <textarea className="campo area-colar" value={texto} placeholder="Clique aqui e cole (Ctrl+V) as linhas copiadas do CONTROLE DE CAIXA"
                    onChange={(e) => setTexto(e.target.value)}
                    onPaste={(e) => { const t = e.clipboardData.getData("text"); setTexto(t); e.preventDefault(); ler(t); }} />
          <div className="acoes-linha">
            <label className="nota">A partir de <DataInput valor={desde} aoMudar={(v) => v && mudarDesde(v)} /></label>
            <button className="botao" disabled={!texto.trim()} onClick={() => ler(texto)}><ClipboardPaste size={16} /> Ler linhas</button>
            <span className="nota">Pode colar a aba inteira (Ctrl+A, Ctrl+C): só aparece o que é a partir dessa data e ainda não está na Hoth.</span>
          </div>
        </div>
      )}

      {linhas && (
        <>
          <div className="grade-metricas">
            <Metrica rotulo="Linhas no período" valor={resumo.total}
                     detalhe={`${resumo.jaExistem} já estão na Hoth${resumo.fora ? ` · ${resumo.fora} antes do período` : ""}`} />
            <Metrica rotulo="Marcadas para gravar" valor={resumo.marcadas} tom="ok" />
            <Metrica rotulo="Entradas / saídas marcadas" valor={dinheiro(resumo.entradas + resumo.saidas)}
                     detalhe={`+${dinheiro(resumo.entradas)} / ${dinheiro(resumo.saidas)}`} />
            <Metrica rotulo="Marcadas sem conta" valor={resumo.semConta} tom={resumo.semConta ? "alerta" : "ok"}
                     detalhe="entram como Sem classificação" />
          </div>
          <div className="barra-caixa">
            <label className="nota">A partir de <DataInput valor={desde} aoMudar={(v) => v && mudarDesde(v)} /></label>
            <label className="nota"><input type="checkbox" checked={todas} onChange={(e) => setTodas(e.target.checked)} /> Mostrar também o que já está na Hoth</label>
            {resumo.correcoes > 0 && <span className="mini alerta">{resumo.correcoes} possível(is) correção(ões) de lançamento já gravado: confira antes de marcar</span>}
            <span className="nota">Ctrl+V aqui lê uma nova seleção</span>
            <button className="botao discreto" onClick={() => setLinhas(null)}>Limpar</button>
          </div>
          <div className="tabela-rolagem">
            <table className="tabela tabela-caixa">
              <thead>
                <tr><th>Gravar</th><th>Data</th><th>Descrição</th><th className="num">Valor</th><th>Conta</th><th>Situação</th></tr>
              </thead>
              <tbody>
                {linhas.map((l, i) => {
                  if (!todas && (l.fora_periodo || (l.ja_existe && !l.incluir))) return null;
                  const s = situacao(l);
                  return (
                    <tr key={i} className={l.incluir && (!l.conta || l.avisos.length) ? "linha-pendente" : l.incluir ? "" : "linha-fora"}>
                      <td><input type="checkbox" checked={l.incluir} aria-label={`Gravar linha ${l.linha}`}
                                 onChange={(e) => mudar(i, { incluir: e.target.checked })} /></td>
                      <td><DataInput valor={l.data} aoMudar={(v) => mudar(i, { data: v })} /></td>
                      <td>
                        <input className="campo campo-desc" value={l.descricao} onChange={(e) => mudar(i, { descricao: e.target.value })} />
                        {l.avisos.map((a) => <div key={a} className="mini alerta">{a}</div>)}
                        {l.correcao_de && <div className="mini alerta">Na Hoth no mesmo dia: {l.correcao_de}. Se for correção, ajuste lá em Lançamentos em vez de lançar de novo.</div>}
                        {l.ja_existe && l.incluir && <div className="mini alerta">Será lançado de novo (repetido de propósito)</div>}
                      </td>
                      <td><input className={`campo campo-valor num ${l.valor < 0 ? "neg" : "pos"}`} type="number" step="0.01"
                                 value={l.valor} onChange={(e) => mudar(i, { valor: Number(e.target.value) })} /></td>
                      <td className="col-conta">
                        <ContaInput valor={l.conta} contas={contas} aoMudar={(v) => mudar(i, { conta: v, avisos: l.avisos.filter((a) => !a.startsWith("conta")) })} />
                        {l.plano_original && l.plano_original !== l.conta && <div className="mini">No CONTROLE: {l.plano_original}</div>}
                      </td>
                      <td className="mini"><span className={`etiqueta ${s.classe}`}>{s.texto}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {confirmar && linhas && (
        <Modal titulo="Gravar na planilha" aoFechar={() => setConfirmar(false)}
               acoes={<><button className="botao" onClick={() => setConfirmar(false)}>Voltar</button>
                 <button className="botao primario" onClick={gravar}><Save size={16} /> Gravar</button></>}>
          <p><strong>{resumo.marcadas}</strong> lançamentos da Caixa Loja serão gravados (saldo {dinheiro(resumo.entradas + resumo.saidas)}).</p>
          {resumo.semConta > 0 && <p className="alerta">{resumo.semConta} ficarão sem classificação e podem ser classificados depois em Lançamentos.</p>}
          <p className="nota">Antes de gravar, a versão atual da planilha vai para a pasta BKP. A planilha precisa estar fechada no Excel.</p>
        </Modal>
      )}
    </section>
  );
}
