import { Brain, History, ListTree, Tags } from "lucide-react";
import { Aprendizado } from "./Aprendizado";
import { Categorias } from "./Categorias";
import { PlanoContas } from "./PlanoContas";
import { Versoes } from "./Versoes";

export type SecaoConfig = "categorias-fluxo" | "categorias-lancamentos" | "aprendizado" | "versoes";

export const SECOES: { id: SecaoConfig; rotulo: string; icone: typeof Tags }[] = [
  { id: "categorias-fluxo", rotulo: "Categorias – Fluxo de Caixa", icone: Tags },
  { id: "categorias-lancamentos", rotulo: "Categorias – Lançamentos", icone: ListTree },
  { id: "aprendizado", rotulo: "Aprendizado das classificações", icone: Brain },
  { id: "versoes", rotulo: "Versões e auditoria", icone: History },
];

export function Configuracoes({ secao, ir, contas, bancos, aoMudar }: {
  secao: SecaoConfig; ir: (s: SecaoConfig) => void; contas: string[]; bancos: string[]; aoMudar: () => void;
}) {
  return (
    <section className="pagina">
      <header className="pagina-cab"><div><h1>Configurações</h1></div></header>
      <div className="config-abas" role="tablist">
        {SECOES.map(({ id, rotulo, icone: Icone }) => (
          <button key={id} role="tab" aria-selected={secao === id} className={`config-aba ${secao === id ? "ativa" : ""}`} onClick={() => ir(id)}>
            <Icone size={15} /> {rotulo}
          </button>
        ))}
      </div>
      <div className="config-conteudo">
        {secao === "categorias-fluxo" && <Categorias />}
        {secao === "categorias-lancamentos" && <PlanoContas aoMudar={aoMudar} />}
        {secao === "aprendizado" && <Aprendizado contas={contas} bancos={bancos} />}
        {secao === "versoes" && <Versoes aoMudar={aoMudar} />}
      </div>
    </section>
  );
}
