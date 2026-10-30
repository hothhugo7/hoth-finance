import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCheck, CreditCard, FileUp, Save, Search, Undo2, XCircle } from "lucide-react";
import { api, dataBR, dinheiro, ListaTitulos, PreviaRet, Titulo } from "../api";
import { Carregando, DataInput, Metrica, Modal, useAviso } from "../components/ui";

// Ordem dos filtros: o que pede ação primeiro.
const FILTROS: { id: string; rotulo: string; tom?: "alerta" | "ok" }[] = [
  { id: "vencido", rotulo: "Vencidos em aberto", tom: "alerta" },
  { id: "baixado_sem_prova", rotulo: "Baixados sem prova", tom: "alerta" },
  { id: "pago_provavel", rotulo: "Pagos prováveis" },
  { id: "pago_diferenca", rotulo: "Pagos com diferença" },
  { id: "no_malote", rotulo: "No malote" },
  { id: "a_vencer", rotulo: "A vencer" },
  { id: "aguardando_fatura", rotulo: "Aguardando fatura" },
  { id: "pago_conferido,pago_fora", rotulo: "Pagos", tom: "ok" },
  { id: "cancelado", rotulo: "Cancelados" },
];

const ETIQUETA: Record<string, string> = {
  pago_conferido: "etiqueta-ok", pago_fora: "etiqueta-ok", pago_provavel: "etiqueta-media", pago_diferenca: "etiqueta-media",
  no_malote: "etiqueta-media", aguardando_fatura: "etiqueta-media", a_vencer: "", cancelado: "",
  vencido: "etiqueta-pend", baixado_sem_prova: "etiqueta-pend",
};

export function ContasPagar() {
  const [dados, setDados] = useState<ListaTitulos | null>(null);
  const [filtro, setFiltro] = useState("vencido");
  const [busca, setBusca] = useState("");
  const [ate, setAte] = useState<string | null>(null);
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [previa, setPrevia] = useState<PreviaRet | null>(null);
  const [acao, setAcao] = useState<{ marca: string; titulo: string } | null>(null);
  const [obs, setObs] = useState("");
  const [ocupado, setOcupado] = useState("");
  const entrada = useRef<HTMLInputElement>(null);
  const avisar = useAviso();

  const carregar = useCallback(async () => {
    try {
      setDados(await api.cpTitulos({ situacao: filtro, busca, ate: ate ?? "" }));
      setMarcados(new Set());
    } catch (e) {
      avisar("erro", (e as Error).message);
    }
  }, [filtro, busca, ate, avisar]);

  useEffect(() => { carregar(); }, [carregar]);

  const rodar = async (texto: string, f: () => Promise<string>) => {
    setOcupado(texto);
    try {
      avisar("ok", await f());
      await carregar();
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado("");
    }
  };

  const enviar = async (arquivo: File) => {
    setOcupado("Lendo o relatório do RET…");
    try {
      setPrevia(await api.cpPrevia(arquivo));
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado("");
    }
  };

  const importar = () => {
    if (!previa) return;
    const token = previa.token;
    setPrevia(null);
    rodar("Gravando os títulos e conferindo os pagamentos…", async () => (await api.cpImportar(token)).detalhe);
  };

  const marcar = (marca: string, ids: string[], observacao = "", lancamento = "") =>
    rodar("Gravando…", async () => `${(await api.cpMarcar(ids, marca, observacao, lancamento)).alterados} título(s) atualizados`);

  const resumo = (ids: string) => {
    const r = (dados?.resumo ?? []).filter((x) => ids.split(",").includes(x.situacao));
    return { quantidade: r.reduce((s, x) => s + x.quantidade, 0), valor: r.reduce((s, x) => s + x.valor, 0) };
  };
  const itens = dados?.itens ?? [];
  const todos = itens.length > 0 && itens.every((t) => marcados.has(t.id));
  const alternar = (id: string) =>
    setMarcados((m) => { const n = new Set(m); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const sel = [...marcados];

  return (
    <section className="pagina">
      <header className="pagina-cab">
        <div>
          <h1>Contas a Pagar</h1>
          <p className="sub">
            Títulos do RET conferidos com extratos, lotérica, comprovantes e malotes.{" "}
            {dados?.ultima_importacao && <>Última importação: {dataBR(dados.ultima_importacao.quando)}.</>}
          </p>
        </div>
        <button className="botao primario" disabled={!!ocupado} onClick={() => entrada.current?.click()}>
          <FileUp size={16} /> Importar RET (contas em aberto)
        </button>
        <input ref={entrada} type="file" accept=".xls" hidden
               onChange={(e) => { const f = e.target.files?.[0]; if (f) enviar(f); e.target.value = ""; }} />
      </header>

      {ocupado && <Carregando texto={ocupado} />}

      {dados && !dados.existe && !ocupado && (
        <div className="cartao">
          <p>Nenhum título ainda. No RET, exporte <strong>Contas a Pagar</strong> em aberto (.xls) e clique em
            <strong> Importar RET</strong>. Os títulos ficam em <code>{dados.arquivo}</code>.</p>
        </div>
      )}

      {dados && dados.existe && (
        <>
          <div className="grade-metricas grade-situacoes">
            {FILTROS.map((f) => {
              const r = resumo(f.id);
              return (
                <button key={f.id} className={`metrica-botao ${filtro === f.id ? "ativa" : ""}`} onClick={() => setFiltro(f.id)}>
                  <Metrica rotulo={f.rotulo} valor={r.quantidade} detalhe={`R$ ${dinheiro(r.valor)}`}
                           tom={r.quantidade ? f.tom : undefined} />
                </button>
              );
            })}
          </div>

          <div className="barra-caixa">
            <label className="campo-busca"><Search size={15} />
              <input value={busca} placeholder="Fornecedor, documento ou valor" onChange={(e) => setBusca(e.target.value)} />
            </label>
            <label className="nota">Vencimento até <DataInput valor={ate} aoMudar={setAte} permitirVazio /></label>
            <button className={`botao discreto ${filtro === "" ? "ativo" : ""}`} onClick={() => setFiltro("")}>Todos</button>
            <span className="nota">{dados.total} título(s) · R$ {dinheiro(dados.soma)}</span>
          </div>

          {sel.length > 0 && (
            <div className="barra-caixa barra-acoes">
              <strong>{sel.length} selecionado(s)</strong>
              <button className="botao" onClick={() => marcar("confirmado", sel)}><CheckCheck size={15} /> Confirmar pagamento</button>
              <button className="botao" onClick={() => marcar("aguardando_fatura", sel)}><CreditCard size={15} /> Aguardando fatura</button>
              <button className="botao" onClick={() => { setObs(""); setAcao({ marca: "pago_fora", titulo: "Pago fora (baixa manual)" }); }}>Pago fora</button>
              <button className="botao" onClick={() => { setObs(""); setAcao({ marca: "cancelado", titulo: "Cancelar títulos" }); }}><XCircle size={15} /> Cancelado</button>
              <button className="botao discreto" onClick={() => marcar("", sel)}><Undo2 size={15} /> Tirar marcação</button>
            </div>
          )}

          <div className="tabela-rolagem">
            <table className="tabela tabela-titulos">
              <thead>
                <tr>
                  <th><input type="checkbox" checked={todos} aria-label="Marcar todos"
                             onChange={() => setMarcados(todos ? new Set() : new Set(itens.map((t) => t.id)))} /></th>
                  <th>Vencimento</th><th>Fornecedor</th><th className="num">Valor</th><th>Situação</th><th>Pagamento / prova</th>
                </tr>
              </thead>
              <tbody>
                {itens.map((t) => <Linha key={t.id} t={t} marcado={marcados.has(t.id)} alternar={alternar}
                                         confirmar={(lanc) => marcar("confirmado", [t.id], "", lanc)} />)}
              </tbody>
            </table>
            {itens.length === 0 && <p className="nota vazio">Nenhum título nesta situação.</p>}
          </div>
        </>
      )}

      {previa && (
        <Modal titulo="Importar contas em aberto do RET" aoFechar={() => setPrevia(null)}
               acoes={<><button className="botao" onClick={() => setPrevia(null)}>Voltar</button>
                 <button className="botao primario" onClick={importar}><Save size={16} /> Gravar</button></>}>
          <p><strong>{previa.lidos}</strong> títulos em aberto, R$ {dinheiro(previa.total)}, vencimentos de {dataBR(previa.de)} a {dataBR(previa.ate)}.</p>
          <ul className="lista-previa">
            <li><strong>{previa.novos}</strong> novos (R$ {dinheiro(previa.valor_novos)})</li>
            <li><strong>{previa.mudaram.length}</strong> com valor ou vencimento alterado</li>
            <li><strong>{previa.sairam.length}</strong> saíram do RET (baixados) — o app procura o pagamento de cada um</li>
          </ul>
          {previa.mudaram.length > 0 && (
            <details><summary className="nota">Ver alterados</summary>
              {previa.mudaram.map((m, i) => <div key={i} className="mini">{m.fornecedor} · {dataBR(m.vencimento_antes)} → {dataBR(m.vencimento)} · {dinheiro(m.valor_antes)} → {dinheiro(m.valor)}</div>)}
            </details>
          )}
          <p className="nota">Antes de gravar, a versão atual do arquivo de títulos vai para o backup. Nenhum título é apagado.</p>
        </Modal>
      )}

      {acao && (
        <Modal titulo={acao.titulo} aoFechar={() => setAcao(null)}
               acoes={<><button className="botao" onClick={() => setAcao(null)}>Voltar</button>
                 <button className="botao primario" onClick={() => { const a = acao; setAcao(null); marcar(a.marca, sel, obs); }}>Gravar</button></>}>
          <p>{sel.length} título(s).</p>
          <label className="nota">Observação (como foi pago, motivo)
            <input className="campo campo-desc" value={obs} autoFocus onChange={(e) => setObs(e.target.value)} />
          </label>
        </Modal>
      )}
    </section>
  );
}

function Linha({ t, marcado, alternar, confirmar }: {
  t: Titulo; marcado: boolean; alternar: (id: string) => void; confirmar: (lancamento: string) => void;
}) {
  return (
    <tr className={t.situacao === "vencido" || t.situacao === "baixado_sem_prova" ? "linha-pendente" : ""}>
      <td><input type="checkbox" checked={marcado} onChange={() => alternar(t.id)} aria-label={`Marcar ${t.fornecedor}`} /></td>
      <td className="nowrap">{dataBR(t.vencimento)}</td>
      <td>
        <div>{t.fornecedor}</div>
        <div className="mini">Doc. {t.documento || "—"} · parcela {t.parcela}{t.duplicata ? ` · ${t.duplicata}` : ""}{t.banco_ret ? ` · RET: ${t.banco_ret}` : ""}{t.conta ? ` · ${t.conta}` : ""}</div>
        {t.historico && <div className="mini">{t.historico}</div>}
      </td>
      <td className="num nowrap">{dinheiro(t.valor)}</td>
      <td><span className={`etiqueta ${ETIQUETA[t.situacao] ?? ""}`}>{t.situacao_texto}</span>
        {t.marca && <div className="mini">marcado por você</div>}</td>
      <td className="mini">
        {t.data_pagamento && <div><strong>{dataBR(t.data_pagamento)}</strong> · {t.banco_pagamento} · {t.descricao_pagamento}{t.valor_pago != null && t.valor_pago !== t.valor ? ` · pago ${dinheiro(t.valor_pago)}` : ""}</div>}
        <div>{t.prova}{t.observacao ? ` · ${t.observacao}` : ""}</div>
        {t.situacao === "pago_provavel" && <button className="link" onClick={() => confirmar(t.id_lancamento)}><CheckCheck size={12} /> confirmar</button>}
        {t.candidatos.map((c) => (
          <button key={c.id} className="link" onClick={() => confirmar(c.id)}>
            É este: {dataBR(c.data)} · {c.banco} · {c.descricao}
          </button>
        ))}
      </td>
    </tr>
  );
}
