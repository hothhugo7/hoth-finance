import { ClipboardPaste, ExternalLink, FileUp, Rows3 } from "lucide-react";
import { api, dataBR, dinheiro, Estado } from "../api";
import { Carregando, Metrica, useAviso } from "../components/ui";
import type { Pagina } from "../App";

export function Painel({ estado, ir }: { estado: Estado | null; ir: (p: Pagina) => void }) {
  const avisar = useAviso();
  if (!estado) return <Carregando texto="Lendo a planilha…" />;
  const abrir = async () => {
    try { avisar("info", (await api.abrirPlanilha("oficial")).detalhe); } catch (e) { avisar("erro", (e as Error).message); }
  };
  const ult = estado.ultima_importacao;
  return (
    <section className="pagina">
      <header className="pagina-cab">
        <div>
          <h1>Painel</h1>
          <p className="sub">Planilha em uso: <code>{estado.planilha}</code>{" "}
            <button className="link" onClick={abrir}><ExternalLink size={12} /> Abrir planilha</button></p>
        </div>
        <button className="botao primario" onClick={() => ir("importar")}><FileUp size={16} /> Importar extrato</button>
      </header>

      <div className="grade-metricas">
        <Metrica rotulo="Lançamentos" valor={estado.lancamentos.toLocaleString("pt-BR")} detalhe={`ano ${estado.ano}`} />
        <Metrica rotulo="Sem classificação" valor={estado.pendentes} tom={estado.pendentes ? "alerta" : "ok"}
                 detalhe={`R$ ${dinheiro(estado.pendentes_valor)}`} />
        <Metrica rotulo="Última importação" valor={ult ? dataBR(ult[0]).slice(0, 10) : "—"}
                 detalhe={ult ? ult[2] : "nenhuma ainda"} />
        <Metrica rotulo="Versões guardadas" valor={estado.backups} detalhe="pasta BKP" />
      </div>

      <div className="duas-colunas">
        <div className="cartao">
          <h2>Bancos</h2>
          <table className="tabela">
            <thead><tr><th>Banco</th><th className="num">Lançamentos</th><th>Último lançamento</th></tr></thead>
            <tbody>
              {estado.bancos.map((b) => (
                <tr key={b.banco}><td>{b.banco}</td><td className="num">{b.lancamentos.toLocaleString("pt-BR")}</td>
                  <td>{dataBR(b.ultima_data)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="cartao">
          <h2>Atalhos</h2>
          <div className="atalhos">
            <button className="atalho" onClick={() => ir("lancamentos")}>
              <Rows3 size={18} /><span><strong>Revisar sem classificação</strong><small>{estado.pendentes} lançamentos aguardando conta</small></span>
            </button>
            <button className="atalho" onClick={() => ir("caixa")}>
              <ClipboardPaste size={18} /><span><strong>Colar Caixa Loja</strong>
                <small>último lançamento: {dataBR(estado.bancos.find((b) => b.banco === "Caixa Loja")?.ultima_data)}</small></span>
            </button>
          </div>
          <p className="nota">Plano de contas, categorias, aprendizado e versões ficam em Configurações (engrenagem, no pé do menu).</p>
        </div>
      </div>
    </section>
  );
}
