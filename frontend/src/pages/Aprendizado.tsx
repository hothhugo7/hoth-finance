import { useCallback, useEffect, useState } from "react";
import { Lock, Search, Trash2 } from "lucide-react";
import { api, Aprendido, Aprendizado as AprendizadoT } from "../api";
import { Carregando, ContaInput, useAviso } from "../components/ui";

// Descrições que o banco repete para pagamentos de fornecedores diferentes.
const GENERICA = /PAGAMENTO DE TITULO|PGTO FORNEC|PAGAMENTO A FORNEC|PAGAMENTO DE BOLETO|^PIX (ENVIADO|RECEBIDO)\s*$|^TED/i;

export function Aprendizado({ contas, bancos }: { contas: string[]; bancos: string[] }) {
  const [dados, setDados] = useState<AprendizadoT | null>(null);
  const [busca, setBusca] = useState("");
  const [banco, setBanco] = useState("");
  const [sentido, setSentido] = useState("saída");
  const [editando, setEditando] = useState<string | null>(null);
  const [conta, setConta] = useState("");
  const [ocupado, setOcupado] = useState("");
  const avisar = useAviso();

  const carregar = useCallback(async () => {
    try { setDados(await api.aprendizado(busca, banco, sentido)); } catch (e) { avisar("erro", (e as Error).message); }
  }, [busca, banco, sentido, avisar]);
  useEffect(() => { const t = setTimeout(carregar, 250); return () => clearTimeout(t); }, [carregar]);

  const regra = async (tipo: string, chave: string, nome: string, c: string | null) => {
    setOcupado("Gravando a regra…");
    try {
      avisar("ok", (await api.salvarRegra(tipo, chave, nome, c)).detalhe);
      setEditando(null);
      await carregar();
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado("");
    }
  };

  const chaveLinha = (a: Aprendido) => `${a.banco}|${a.descricao}|${a.sentido}`;

  return (
    <div>
      <p className="sub">O app aprende com os lançamentos já classificados: mesma descrição (no mesmo banco e sentido) recebe a conta mais
        usada, se for consistente. Aqui você vê o que ele aprendeu e pode <strong>fixar</strong> uma conta (vale sempre, antes do
        aprendizado), mandar <strong>sempre revisar</strong> ou tirar a regra. Corrigir lançamentos na tela Lançamentos também ensina.</p>

      {ocupado && <Carregando texto={ocupado} />}

      {dados && dados.regras.length > 0 && (
        <div className="cartao">
          <h2><Lock size={15} /> Regras fixas ({dados.regras.length})</h2>
          <table className="tabela">
            <tbody>
              {dados.regras.map((r) => (
                <tr key={r.chave}>
                  <td className="mini">{r.tipo === "fornecedor" ? `fornecedor ${r.chave}` : "descrição"}</td>
                  <td>{r.nome}</td>
                  <td>{r.conta || <span className="etiqueta etiqueta-media">sempre revisar</span>}</td>
                  <td><button className="icone" aria-label="Tirar regra" onClick={() => regra(r.tipo, r.chave, r.nome, null)}><Trash2 size={13} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="barra-caixa">
        <label className="campo-busca"><Search size={15} />
          <input value={busca} placeholder="Descrição (ex.: ASSAI, PIX RECEBIDO)" onChange={(e) => setBusca(e.target.value)} />
        </label>
        <select className="campo" value={banco} onChange={(e) => setBanco(e.target.value)}>
          <option value="">Todos os bancos</option>
          {bancos.map((b) => <option key={b}>{b}</option>)}
        </select>
        <select className="campo" value={sentido} onChange={(e) => setSentido(e.target.value)}>
          <option value="">Entradas e saídas</option><option value="saída">Saídas</option><option value="entrada">Entradas</option>
        </select>
        {dados && <span className="nota">{dados.total} descrições aprendidas · divididas entre contas aparecem primeiro</span>}
      </div>

      {dados && (
        <div className="tabela-rolagem">
          <table className="tabela tabela-previa">
            <thead><tr><th>Descrição</th><th className="num">Vezes</th><th>Conta aprendida</th><th>Regra</th></tr></thead>
            <tbody>
              {dados.aprendidos.map((a) => {
                const k = chaveLinha(a);
                return (
                  <tr key={k} className={a.consistencia < 0.95 ? "linha-pendente" : ""}>
                    <td>{a.descricao}<div className="mini">{a.banco} · {a.sentido}</div></td>
                    <td className="num">{a.vezes}</td>
                    <td>{a.conta} <span className="mini">({Math.round(a.consistencia * 100)}%)</span>
                      {a.outras.map((o) => <div key={o.conta} className="mini">também {o.conta} ({o.vezes})</div>)}
                      {a.consistencia < 0.95 && !a.regra && <div className="mini alerta">dividida: o app não classifica sozinho</div>}
                      {GENERICA.test(a.descricao) && <div className="mini alerta">descrição genérica (vale para fornecedores diferentes): não fixe
                        aqui — o fornecedor vem do comprovante ou do código</div>}</td>
                    <td className="col-conta">
                      {a.regra && <div className="mini"><Lock size={11} /> regra fixa {a.regra.startsWith("desc:") ? "da descrição" : "do fornecedor"}</div>}
                      {editando === k ? (
                        <div className="acoes-linha">
                          <ContaInput valor={conta} contas={contas} aoMudar={setConta} autoFocus />
                          <button className="botao" disabled={!conta} onClick={() => regra("descricao", a.descricao, a.descricao, conta)}>Fixar</button>
                          <button className="botao discreto" onClick={() => setEditando(null)}>Cancelar</button>
                        </div>
                      ) : (
                        <div className="sugestoes">
                          <button className="chip" onClick={() => { setEditando(k); setConta(a.conta); }}>Fixar conta…</button>
                          <button className="chip" onClick={() => regra("descricao", a.descricao, a.descricao, "")}>Sempre revisar</button>
                          {a.regra && <button className="chip" onClick={() => regra(a.regra!.startsWith("desc:") ? "descricao" : "fornecedor", a.regra!, a.descricao, null)}>Tirar regra</button>}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
