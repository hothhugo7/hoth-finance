import { useCallback, useEffect, useState } from "react";
import { FileSpreadsheet, Lightbulb, Plus, Trash2 } from "lucide-react";
import { api, dataBR, dinheiro, Fluxo, valorBR } from "../api";
import { Carregando, DataInput, Metrica, useAviso } from "../components/ui";

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const somar = (d: Date, dias: number) => { const n = new Date(d); n.setDate(n.getDate() + dias); return n; };
const hoje = () => new Date(new Date().toDateString());
const titulo = (c: string) => c.charAt(0) + c.slice(1).toLowerCase();

const ATALHOS: { rotulo: string; periodo: () => [Date, Date] }[] = [
  { rotulo: "Próximos 7 dias", periodo: () => [hoje(), somar(hoje(), 6)] },
  { rotulo: "Próximos 30 dias", periodo: () => [hoje(), somar(hoje(), 29)] },
  { rotulo: "Este mês", periodo: () => { const h = hoje(); return [new Date(h.getFullYear(), h.getMonth(), 1), new Date(h.getFullYear(), h.getMonth() + 1, 0)]; } },
  { rotulo: "Próximo mês", periodo: () => { const h = hoje(); return [new Date(h.getFullYear(), h.getMonth() + 1, 1), new Date(h.getFullYear(), h.getMonth() + 2, 0)]; } },
];

export function FluxoCaixa() {
  const [de, setDe] = useState<string | null>(iso(hoje()));
  const [ate, setAte] = useState<string | null>(iso(somar(hoje(), 29)));
  const [dados, setDados] = useState<Fluxo | null>(null);
  const [verTitulos, setVerTitulos] = useState(false);
  const [ocupado, setOcupado] = useState("");
  const [nova, setNova] = useState({ data: iso(hoje()) as string | null, descricao: "", valor: "", forma: "", repetirAte: null as string | null });
  const avisar = useAviso();

  const carregar = useCallback(async () => {
    if (!de || !ate) return;
    try { setDados(await api.fluxo(de, ate)); } catch (e) { avisar("erro", (e as Error).message); }
  }, [de, ate, avisar]);
  useEffect(() => { carregar(); }, [carregar]);

  const rodar = async (texto: string, f: () => Promise<{ detalhe: string; aviso_fluxo?: string }>) => {
    setOcupado(texto);
    try {
      const r = await f();
      avisar("ok", r.detalhe);
      if (r.aviso_fluxo) avisar("erro", r.aviso_fluxo);
      await carregar();
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado("");
    }
  };

  const incluir = () => {
    const v = valorBR(nova.valor);
    if (!nova.data || !nova.descricao.trim() || v === null || v <= 0) { avisar("erro", "Preencha data, descrição e valor."); return; }
    rodar("Gravando a entrada…", () => api.fluxoEntradas([{ data: nova.data!, descricao: nova.descricao, valor: v, forma: nova.forma, repetir_ate: nova.repetirAte }]))
      .then(() => setNova((n) => ({ ...n, descricao: "", valor: "", repetirAte: null })));
  };

  const diaSemana = nova.data ? ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"][new Date(`${nova.data}T12:00`).getDay()] : "";
  const sugestaoDia = dados && diaSemana ? dados.sugestao.por_dia_semana[diaSemana] : 0;
  const cats = dados?.categorias ?? [];

  return (
    <section className="pagina">
      <header className="pagina-cab">
        <div>
          <h1>Fluxo de Caixa</h1>
          <p className="sub">Quanto entra e quanto sai no período. Até ontem, o que foi pago (realizado); de hoje em diante, os boletos em
            aberto e as entradas que você lançar (projetado).</p>
        </div>
        <button className="botao" disabled={!!ocupado} onClick={() => rodar("Atualizando a planilha…", api.fluxoPlanilha)}
                title={dados?.planilha}>
          <FileSpreadsheet size={16} /> Atualizar planilha
        </button>
      </header>

      {ocupado && <Carregando texto={ocupado} />}

      <div className="barra-caixa">
        <label className="nota">De <DataInput valor={de} aoMudar={setDe} /></label>
        <label className="nota">Até <DataInput valor={ate} aoMudar={setAte} /></label>
        {ATALHOS.map((a) => (
          <button key={a.rotulo} className="botao discreto" onClick={() => { const [x, y] = a.periodo(); setDe(iso(x)); setAte(iso(y)); }}>{a.rotulo}</button>
        ))}
      </div>

      {dados?.aviso_planilha && <p className="mini alerta">{dados.aviso_planilha}</p>}
      {dados && dados.sem_categoria > 0 && (
        <p className="mini alerta">{dados.sem_categoria} boleto(s) do período sem categoria — classifique em <a className="link" href="#/categorias">Categorias</a>.</p>
      )}

      {dados && (
        <>
          <div className="grade-metricas">
            <Metrica rotulo="Entradas" valor={dinheiro(dados.totais.entradas)} tom="ok" detalhe="lançadas por você" />
            <Metrica rotulo="Saídas" valor={dinheiro(dados.totais.saidas)} tom="alerta" detalhe={`${dados.titulos.length} boleto(s)`} />
            <Metrica rotulo="Resultado do período" valor={dinheiro(dados.totais.resultado)} tom={dados.totais.resultado < 0 ? "alerta" : "ok"} />
            {dados.menor_acumulado && <Metrica rotulo="Pior momento" valor={dinheiro(dados.menor_acumulado.valor)}
                                               detalhe={`em ${dataBR(dados.menor_acumulado.data)} (acumulado do período)`} />}
          </div>

          <div className="duas-colunas">
            <div className="cartao">
              <h2>Saídas por categoria</h2>
              <table className="tabela">
                <tbody>
                  {cats.map((c) => (
                    <tr key={c} className={c === "SEM CATEGORIA" && dados.totais.por_categoria[c] ? "linha-pendente" : ""}>
                      <td>{titulo(c)}</td><td className="num">{dinheiro(dados.totais.por_categoria[c] ?? 0)}</td>
                      <td className="num mini">{dados.totais.saidas ? `${((dados.totais.por_categoria[c] ?? 0) / dados.totais.saidas * 100).toFixed(0)}%` : ""}</td>
                    </tr>
                  ))}
                  <tr><td><strong>Total</strong></td><td className="num"><strong>{dinheiro(dados.totais.saidas)}</strong></td><td /></tr>
                </tbody>
              </table>
              {dados.meses.length > 1 && (
                <table className="tabela tabela-meses">
                  <thead><tr><th>Mês</th><th className="num">Entradas</th><th className="num">Saídas</th><th className="num">Resultado</th></tr></thead>
                  <tbody>{dados.meses.map((m) => (
                    <tr key={m.rotulo}><td>{m.rotulo}</td><td className="num">{dinheiro(m.entradas)}</td><td className="num">{dinheiro(m.saidas)}</td>
                      <td className={`num ${m.resultado < 0 ? "neg" : "pos"}`}>{dinheiro(m.resultado)}</td></tr>
                  ))}</tbody>
                </table>
              )}
            </div>

            <div className="cartao">
              <h2>Entradas previstas</h2>
              <div className="form-entrada">
                <label className="nota">Data <DataInput valor={nova.data} aoMudar={(v) => setNova((n) => ({ ...n, data: v }))} /></label>
                <label className="nota">Descrição <input className="campo" value={nova.descricao} placeholder="Vendas, cartões, cliente…"
                                                        onChange={(e) => setNova((n) => ({ ...n, descricao: e.target.value }))} /></label>
                <label className="nota">Valor <input className="campo campo-valor" value={nova.valor} placeholder="0,00"
                                                    onChange={(e) => setNova((n) => ({ ...n, valor: e.target.value }))}
                                                    onKeyDown={(e) => e.key === "Enter" && incluir()} /></label>
                <label className="nota">Forma <input className="campo campo-dias" value={nova.forma} placeholder="Pix"
                                                    onChange={(e) => setNova((n) => ({ ...n, forma: e.target.value }))} /></label>
                <label className="nota">Repetir toda semana até <DataInput valor={nova.repetirAte} permitirVazio
                                                                            aoMudar={(v) => setNova((n) => ({ ...n, repetirAte: v }))} /></label>
                <button className="botao" disabled={!!ocupado} onClick={incluir}><Plus size={15} /> Incluir</button>
              </div>
              {sugestaoDia > 0 && (
                <div className="card-sugestao">
                  <Lightbulb size={13} /> Sugestão: média de vendas de {diaSemana.toLowerCase()} nas últimas {dados.sugestao.semanas} semanas
                  ≈ R$ {dinheiro(sugestaoDia)}
                  <button className="link" onClick={() => setNova((n) => ({ ...n, valor: dinheiro(sugestaoDia), descricao: n.descricao || "Vendas (média)" }))}>usar</button>
                </div>
              )}
              <table className="tabela tabela-entradas">
                <tbody>
                  {dados.entradas_lancadas.filter((e) => (!de || e.data >= de) && (!ate || e.data <= ate)).map((e) => (
                    <tr key={e.id}>
                      <td className="nowrap">{dataBR(e.data)}</td><td>{e.descricao}<span className="mini"> {e.forma}</span></td>
                      <td className="num">{dinheiro(e.valor)}</td>
                      <td><button className="icone" aria-label="Remover entrada" onClick={() => rodar("Removendo…", () => api.fluxoEntradas([], [e.id]))}><Trash2 size={13} /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <h2 className="titulo-secao">Dia a dia</h2>
          <div className="tabela-rolagem">
            <table className="tabela tabela-fluxo">
              <thead>
                <tr><th>Data</th><th className="num">Entradas</th>{cats.map((c) => <th key={c} className="num">{titulo(c)}</th>)}
                  <th className="num">Saídas</th><th className="num">Resultado</th><th className="num">Acumulado</th></tr>
              </thead>
              <tbody>
                {dados.dias.map((d) => (
                  <tr key={d.data} className={`fluxo-${d.tipo}`}>
                    <td className="nowrap">{dataBR(d.data)} <span className="mini">{d.dia}</span></td>
                    <td className="num">{d.entradas ? dinheiro(d.entradas) : "—"}</td>
                    {cats.map((c) => <td key={c} className="num">{d.saidas_categoria[c] ? dinheiro(d.saidas_categoria[c]) : "—"}</td>)}
                    <td className="num">{d.saidas ? dinheiro(d.saidas) : "—"}</td>
                    <td className={`num ${d.resultado < 0 ? "neg" : "pos"}`}>{dinheiro(d.resultado)}</td>
                    <td className={`num ${d.acumulado < 0 ? "neg" : "pos"}`}>{dinheiro(d.acumulado)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <button className="link" onClick={() => setVerTitulos((v) => !v)}>{verTitulos ? "Esconder" : "Ver"} os {dados.titulos.length} boletos do período</button>
          {verTitulos && (
            <div className="tabela-rolagem">
              <table className="tabela">
                <tbody>{dados.titulos.map((t) => (
                  <tr key={t.id}>
                    <td className="nowrap">{dataBR(t.data)}</td><td>{t.fornecedor}<div className="mini">venc. {dataBR(t.vencimento)} · {t.tipo}</div></td>
                    <td>{titulo(t.categoria)}</td><td className="num">{dinheiro(t.valor)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <p className="nota">Planilha: <code>{dados.planilha}</code>{dados.planilha_existe ? "" : " (será criada na próxima atualização)"} — atualizada sozinha
            a cada importação do RET, malote, categoria ou entrada.</p>
        </>
      )}
    </section>
  );
}
