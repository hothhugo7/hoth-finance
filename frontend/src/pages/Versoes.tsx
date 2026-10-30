import { useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";
import { api, dataBR, Versoes as TVersoes } from "../api";
import { Carregando, Modal, useAviso } from "../components/ui";

export function Versoes({ aoMudar }: { aoMudar: () => void }) {
  const [dados, setDados] = useState<TVersoes | null>(null);
  const [alvo, setAlvo] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const avisar = useAviso();
  const carregar = () => api.versoes().then(setDados).catch((e) => avisar("erro", e.message));
  useEffect(() => { carregar(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const restaurar = async () => {
    const arq = alvo;
    setAlvo("");
    setOcupado(true);
    try {
      const r = await api.restaurar(arq);
      avisar("ok", `Planilha restaurada. A versão que estava em uso foi guardada em ${r.backup}`);
      aoMudar();
      await carregar();
    } catch (e) {
      avisar("erro", (e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  if (!dados) return <Carregando />;
  return (
    <section className="pagina">
      <header className="pagina-cab">
        <div>
          <h1>Versões e auditoria</h1>
          <p className="sub">Antes de cada gravação a planilha é copiada para a pasta BKP. Restaure se uma importação saiu errada.</p>
        </div>
      </header>
      {ocupado && <Carregando texto="Restaurando…" />}
      <div className="duas-colunas">
        <div className="cartao">
          <h2>Versões guardadas ({dados.backups.length})</h2>
          <table className="tabela">
            <thead><tr><th>Versão</th><th className="num">Tamanho</th><th /></tr></thead>
            <tbody>
              {dados.backups.map((b) => (
                <tr key={b.arquivo}>
                  <td>{b.arquivo.replace(/\.xlsx$/, "").replace(/_/g, " ")}</td>
                  <td className="num mini">{(b.tamanho / 1e6).toFixed(1)} MB</td>
                  <td><button className="botao pequeno" disabled={ocupado} onClick={() => setAlvo(b.arquivo)}><RotateCcw size={14} /> Restaurar</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="cartao">
          <h2>Auditoria</h2>
          <table className="tabela">
            <thead><tr><th>Quando</th><th>Ação</th><th>Detalhe</th></tr></thead>
            <tbody>
              {dados.auditoria.map((a, i) => (
                <tr key={i}><td className="nowrap">{dataBR(a[0])}</td><td className="nowrap">{a[1]}</td><td className="mini">{a[2]}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {alvo && (
        <Modal titulo="Restaurar versão" aoFechar={() => setAlvo("")}
               acoes={<><button className="botao" onClick={() => setAlvo("")}>Voltar</button><button className="botao primario" onClick={restaurar}>Restaurar</button></>}>
          <p>A planilha volta para <strong>{alvo}</strong>.</p>
          <p className="nota">Tudo o que foi gravado depois dessa versão sai da planilha, mas a versão atual também vai para o BKP antes, então dá para voltar.</p>
        </Modal>
      )}
    </section>
  );
}
