import { useCallback, useEffect, useState } from "react";
import { Search, Tags } from "lucide-react";
import { api, dataBR, dinheiro, Lancamento } from "../api";
import { Carregando, ContaInput, Modal, useAviso } from "../components/ui";

const MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
const POR_PAGINA = 100;

export function Lancamentos({ contas, bancos, aoMudar }: { contas: string[]; bancos: string[]; aoMudar: () => void }) {
  const [filtros, setFiltros] = useState({ busca: "", banco: "", mes: 0, conta: "", pendentes: true });
  const [busca, setBusca] = useState("");
  const [pagina, setPagina] = useState(1);
  const [dados, setDados] = useState<{ total: number; soma: number; itens: Lancamento[] } | null>(null);
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [novaConta, setNovaConta] = useState("");
  const [confirmar, setConfirmar] = useState(false);
  const [gravando, setGravando] = useState(false);
  const avisar = useAviso();

  const carregar = useCallback(async () => {
    try {
      setDados(await api.lancamentos({ ...filtros, pagina, por_pagina: POR_PAGINA }));
    } catch (e) {
      avisar("erro", (e as Error).message);
    }
  }, [filtros, pagina, avisar]);

  useEffect(() => { carregar(); }, [carregar]);
  useEffect(() => {
    const t = setTimeout(() => setFiltros((f) => (f.busca === busca ? f : { ...f, busca })), 350);
    return () => clearTimeout(t);
  }, [busca]);
  useEffect(() => { setPagina(1); setMarcados(new Set()); }, [filtros]);

  const mudar = (k: keyof typeof filtros, v: string | number | boolean) => setFiltros((f) => ({ ...f, [k]: v }));
  const alternar = (id: string) => setMarcados((m) => { const n = new Set(m); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const todosMarcados = !!dados && dados.itens.length > 0 && dados.itens.every((l) => marcados.has(l.id));

  const reclassificar = async () => {
    setConfirmar(false);
    setGravando(true);
    try {
      const r = await api.reclassificar([...marcados], novaConta);
      avisar("ok", `${r.alterados} lançamentos agora em ${novaConta || "sem classificação"}`);
      setMarcados(new Set());
      aoMudar();
      await carregar();
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setGravando(false);
    }
  };

  const paginas = dados ? Math.max(1, Math.ceil(dados.total / POR_PAGINA)) : 1;

  return (
    <section className="pagina">
      <header className="pagina-cab">
        <div>
          <h1>Lançamentos</h1>
          <p className="sub">Busque, filtre e reclassifique em lote. Cada alteração guarda a versão anterior no BKP.</p>
        </div>
      </header>

      <div className="filtros">
        <label className="campo-busca"><Search size={15} />
          <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Descrição, observação, conta ou valor" />
        </label>
        <select className="campo" value={filtros.banco} onChange={(e) => mudar("banco", e.target.value)}>
          <option value="">Todos os bancos</option>
          {bancos.map((b) => <option key={b}>{b}</option>)}
        </select>
        <select className="campo" value={filtros.mes} onChange={(e) => mudar("mes", Number(e.target.value))}>
          <option value={0}>Todos os meses</option>
          {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
        </select>
        <div className="campo-conta-filtro">
          <ContaInput valor={filtros.conta} contas={contas} aoMudar={(v) => mudar("conta", v)} placeholder="Qualquer conta" />
        </div>
        <label className="marcar"><input type="checkbox" checked={filtros.pendentes} onChange={(e) => mudar("pendentes", e.target.checked)} /> Só sem classificação</label>
      </div>

      {marcados.size > 0 && (
        <div className="barra-lote">
          <Tags size={16} />
          <span><strong>{marcados.size}</strong> selecionados</span>
          <div className="lote-conta"><ContaInput valor={novaConta} contas={contas} aoMudar={setNovaConta} placeholder="Nova conta (vazio = sem classificação)" /></div>
          <button className="botao primario" disabled={gravando} onClick={() => setConfirmar(true)}>Reclassificar</button>
          <button className="botao discreto" onClick={() => setMarcados(new Set())}>Limpar seleção</button>
        </div>
      )}

      {!dados ? <Carregando /> : (
        <>
          <p className="nota">{dados.total.toLocaleString("pt-BR")} lançamentos · soma R$ {dinheiro(dados.soma)}</p>
          <div className="tabela-rolagem">
            <table className="tabela">
              <thead>
                <tr>
                  <th><input type="checkbox" checked={todosMarcados} aria-label="Selecionar a página"
                             onChange={() => setMarcados((m) => {
                               const n = new Set(m);
                               dados.itens.forEach((l) => (todosMarcados ? n.delete(l.id) : n.add(l.id)));
                               return n;
                             })} /></th>
                  <th>Data</th><th>Banco</th><th>Descrição</th><th className="num">Valor</th><th>Conta</th><th>Origem</th>
                </tr>
              </thead>
              <tbody>
                {dados.itens.map((l) => (
                  <tr key={l.id} className={l.conta ? "" : "linha-pendente"} onClick={() => alternar(l.id)}>
                    <td><input type="checkbox" checked={marcados.has(l.id)} onChange={() => alternar(l.id)} onClick={(e) => e.stopPropagation()} /></td>
                    <td className="nowrap">{dataBR(l.data)}</td>
                    <td className="nowrap">{l.banco}</td>
                    <td>{l.descricao}{l.observacao && <div className="mini">{l.observacao}</div>}</td>
                    <td className={`num nowrap ${l.valor < 0 ? "neg" : "pos"}`}>{dinheiro(l.valor)}</td>
                    <td>{l.conta || <span className="etiqueta etiqueta-pend">sem classificação</span>}</td>
                    <td className="mini">{l.origem}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {paginas > 1 && (
            <div className="paginacao">
              <button className="botao" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>Anterior</button>
              <span>Página {pagina} de {paginas}</span>
              <button className="botao" disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)}>Próxima</button>
            </div>
          )}
        </>
      )}

      {confirmar && (
        <Modal titulo="Reclassificar lançamentos" aoFechar={() => setConfirmar(false)}
               acoes={<><button className="botao" onClick={() => setConfirmar(false)}>Voltar</button>
                 <button className="botao primario" onClick={reclassificar}>Confirmar</button></>}>
          <p>{marcados.size} lançamentos passam para <strong>{novaConta || "sem classificação"}</strong>.</p>
          <p className="nota">A versão atual da planilha vai para o BKP antes. A planilha precisa estar fechada no Excel.</p>
        </Modal>
      )}
    </section>
  );
}
