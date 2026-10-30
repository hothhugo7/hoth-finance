import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Save, Search } from "lucide-react";
import { api, dinheiro, ListaCategorias, semAcento } from "../api";
import { Carregando, Metrica, useAviso } from "../components/ui";

type Filtro = "pendentes" | "base" | "todos";

export function Categorias() {
  const [dados, setDados] = useState<ListaCategorias | null>(null);
  const [mudancas, setMudancas] = useState<Record<string, string>>({});
  const [filtro, setFiltro] = useState<Filtro>("pendentes");
  const [busca, setBusca] = useState("");
  const [nova, setNova] = useState("");
  const [ocupado, setOcupado] = useState("");
  const avisar = useAviso();

  const carregar = useCallback(async () => {
    try {
      const d = await api.cpCategorias();
      setDados(d);
      setMudancas({});
      if (d.pendentes === 0) setFiltro((f) => (f === "pendentes" ? "todos" : f));
    } catch (e) {
      avisar("erro", (e as Error).message);
    }
  }, [avisar]);
  useEffect(() => { carregar(); }, [carregar]);

  const lista = useMemo(() => {
    const termos = semAcento(busca).split(/\s+/).filter(Boolean);
    return (dados?.fornecedores ?? []).filter((f) =>
      (filtro === "todos" || (filtro === "pendentes" ? !f.categoria : f.origem === "base"))
      && termos.every((t) => semAcento(`${f.codigo} ${f.fornecedor}`).includes(t)));
  }, [dados, filtro, busca]);

  const gravar = async (itens: { codigo: string; fornecedor: string; categoria: string }[], novaCat = "") => {
    setOcupado("Gravando as categorias e atualizando o fluxo…");
    try {
      const r = await api.cpSalvarCategorias(itens, novaCat);
      avisar("ok", r.detalhe);
      if (r.aviso_fluxo) avisar("erro", r.aviso_fluxo);
      setNova("");
      await carregar();
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado("");
    }
  };

  const nomes = Object.fromEntries((dados?.fornecedores ?? []).map((f) => [f.codigo, f.fornecedor]));
  const pendentesDeGravar = Object.entries(mudancas).map(([codigo, categoria]) => ({ codigo, fornecedor: nomes[codigo], categoria }));
  const base = (dados?.fornecedores ?? []).filter((f) => f.origem === "base");
  const comSugestao = (dados?.fornecedores ?? []).filter((f) => !f.categoria && f.sugestao && !mudancas[f.codigo]);

  return (
    <section className="pagina">
      <header className="pagina-cab">
        <div>
          <h1>Categorias</h1>
          <p className="sub">Categoria de cada fornecedor do contas a pagar, usada no Fluxo de Caixa. Escolha uma vez; vale para todos
            os boletos do fornecedor.</p>
        </div>
        <button className="botao primario" disabled={!pendentesDeGravar.length || !!ocupado} onClick={() => gravar(pendentesDeGravar)}>
          <Save size={16} /> Gravar ({pendentesDeGravar.length})
        </button>
      </header>

      {ocupado && <Carregando texto={ocupado} />}

      {dados && (
        <>
          <div className="grade-metricas">
            <button className={`metrica-botao ${filtro === "pendentes" ? "ativa" : ""}`} onClick={() => setFiltro("pendentes")}>
              <Metrica rotulo="Sem categoria" valor={dados.pendentes} tom={dados.pendentes ? "alerta" : "ok"} detalhe="fornecedores a classificar" />
            </button>
            <button className={`metrica-botao ${filtro === "base" ? "ativa" : ""}`} onClick={() => setFiltro("base")}>
              <Metrica rotulo="Da versão Base" valor={dados.da_versao_base} detalhe="já valem; confirme para guardar aqui" />
            </button>
            <button className={`metrica-botao ${filtro === "todos" ? "ativa" : ""}`} onClick={() => setFiltro("todos")}>
              <Metrica rotulo="Todos os fornecedores" valor={dados.fornecedores.length} />
            </button>
          </div>

          <div className="barra-caixa">
            <label className="campo-busca"><Search size={15} />
              <input value={busca} placeholder="Código ou fornecedor" onChange={(e) => setBusca(e.target.value)} />
            </label>
            {filtro === "pendentes" && comSugestao.length > 0 && (
              <button className="botao" onClick={() => setMudancas((m) => ({ ...m, ...Object.fromEntries(comSugestao.map((f) => [f.codigo, f.sugestao])) }))}>
                Aplicar as {comSugestao.length} sugestões (pela conta do plano)
              </button>
            )}
            {filtro === "base" && base.length > 0 && (
              <button className="botao" disabled={!!ocupado}
                      onClick={() => gravar(base.map((f) => ({ codigo: f.codigo, fornecedor: f.fornecedor, categoria: f.categoria })))}>
                Confirmar as {base.length} da versão Base
              </button>
            )}
            <label className="nota">Nova categoria
              <input className="campo" value={nova} placeholder="ex.: Impostos" onChange={(e) => setNova(e.target.value)} />
            </label>
            <button className="botao" disabled={!nova.trim() || !!ocupado} onClick={() => gravar([], nova)}><Plus size={15} /> Criar</button>
          </div>

          <div className="tabela-rolagem">
            <table className="tabela">
              <thead><tr><th>Fornecedor</th><th className="num">Boletos</th><th className="num">Em aberto</th><th>Categoria</th></tr></thead>
              <tbody>
                {lista.map((f) => {
                  const atual = mudancas[f.codigo] ?? f.categoria;
                  return (
                    <tr key={f.codigo} className={atual ? "" : "linha-pendente"}>
                      <td>{f.fornecedor}{f.origem === "base" && !mudancas[f.codigo] && <span className="mini"> · da versão Base</span>}
                        {!f.categoria && f.sugestao && <div className="mini">Sugestão: {f.sugestao.charAt(0) + f.sugestao.slice(1).toLowerCase()} (conta {f.conta})</div>}</td>
                      <td className="num">{f.titulos}</td>
                      <td className="num nowrap">{f.em_aberto ? dinheiro(f.em_aberto) : "—"}</td>
                      <td>
                        <div className="sugestoes">
                          {dados.categorias.map((c) => (
                            <button key={c} className={`chip ${atual === c ? "chip-ativo" : ""}`}
                                    onClick={() => setMudancas((m) => ({ ...m, [f.codigo]: c }))}>{c.charAt(0) + c.slice(1).toLowerCase()}</button>
                          ))}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {lista.length === 0 && <p className="nota vazio">Nada nesta lista.</p>}
          </div>
        </>
      )}
    </section>
  );
}
