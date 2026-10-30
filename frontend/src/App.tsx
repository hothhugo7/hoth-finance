import { useCallback, useEffect, useState } from "react";
import { ClipboardPaste, CreditCard, FileUp, LayoutDashboard, Mail, ReceiptText, Rows3, Settings, TrendingUp, TriangleAlert } from "lucide-react";
import { api, Estado } from "./api";
import { ListaContas, Logo, useAviso } from "./components/ui";
import { Painel } from "./pages/Painel";
import { Importar } from "./pages/Importar";
import { ColarCaixa } from "./pages/ColarCaixa";
import { ContasPagar } from "./pages/ContasPagar";
import { Malote } from "./pages/Malote";
import { FaturaCartao } from "./pages/FaturaCartao";
import { FluxoCaixa } from "./pages/FluxoCaixa";
import { Lancamentos } from "./pages/Lancamentos";
import { Configuracoes, SECOES, SecaoConfig } from "./pages/Configuracoes";

export type Pagina = "painel" | "importar" | "caixa" | "pagar" | "malote" | "cartao" | "fluxo" | "lancamentos" | "config";

const MENU: { id: Pagina; rotulo: string; icone: typeof FileUp }[] = [
  { id: "painel", rotulo: "Painel", icone: LayoutDashboard },
  { id: "importar", rotulo: "Importar extrato", icone: FileUp },
  { id: "caixa", rotulo: "Colar Caixa Loja", icone: ClipboardPaste },
  { id: "pagar", rotulo: "Contas a Pagar", icone: ReceiptText },
  { id: "malote", rotulo: "Malote", icone: Mail },
  { id: "cartao", rotulo: "Fatura do cartão", icone: CreditCard },
  { id: "fluxo", rotulo: "Fluxo de Caixa", icone: TrendingUp },
  { id: "lancamentos", rotulo: "Lançamentos", icone: Rows3 },
];

// Endereços antigos continuam funcionando (agora dentro de Configurações).
const ANTIGOS: Record<string, SecaoConfig> = { categorias: "categorias-fluxo", plano: "categorias-lancamentos", versoes: "versoes" };

function rotaDaUrl(): { pagina: Pagina; secao: SecaoConfig } {
  const [p, s] = window.location.hash.replace("#/", "").split("/");
  if (ANTIGOS[p]) return { pagina: "config", secao: ANTIGOS[p] };
  if (p === "config") return { pagina: "config", secao: SECOES.some((x) => x.id === s) ? (s as SecaoConfig) : "categorias-fluxo" };
  return { pagina: MENU.some((m) => m.id === p) ? (p as Pagina) : "painel", secao: "categorias-fluxo" };
}

export default function App() {
  const [rota, setRota] = useState(rotaDaUrl());
  const [estado, setEstado] = useState<Estado | null>(null);
  const [contas, setContas] = useState<string[]>([]);
  const avisar = useAviso();
  const pagina = rota.pagina;

  const atualizar = useCallback(async () => {
    try {
      const [e, c] = await Promise.all([api.estado(), api.contas()]);
      setEstado(e);
      setContas(c);
    } catch (err) {
      avisar("erro", `Não consegui ler a planilha: ${(err as Error).message}`);
    }
  }, [avisar]);

  useEffect(() => {
    atualizar();
    const f = () => setRota(rotaDaUrl());
    window.addEventListener("hashchange", f);
    // F11: tela cheia (na janela do app quem faz é o Python; no navegador, a API do navegador)
    const tecla = (e: KeyboardEvent) => {
      if (e.key !== "F11") return;
      e.preventDefault();
      const py = (window as unknown as { pywebview?: { api?: { tela_cheia?: () => void } } }).pywebview;
      if (py?.api?.tela_cheia) py.api.tela_cheia();
      else if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    };
    window.addEventListener("keydown", tecla);
    return () => { window.removeEventListener("hashchange", f); window.removeEventListener("keydown", tecla); };
  }, [atualizar]);

  const ir = (p: Pagina, secao: SecaoConfig = rota.secao) => {
    window.location.hash = p === "config" ? `#/config/${secao}` : `#/${p}`;
    setRota({ pagina: p, secao });
  };
  const bancos = estado?.bancos.map((b) => b.banco) ?? [];

  return (
    <div className="app">
      <aside className="lateral">
        <Logo />
        <nav>
          {MENU.map(({ id, rotulo, icone: Icone }) => (
            <button key={id} className={`nav-item ${pagina === id ? "ativo" : ""}`} aria-label={rotulo}
                    aria-current={pagina === id ? "page" : undefined} onClick={() => ir(id)}>
              <Icone size={18} />
              <span>{rotulo}</span>
              {id === "lancamentos" && estado && estado.pendentes > 0 && <span className="selo">{estado.pendentes}</span>}
            </button>
          ))}
        </nav>
        <div className="lateral-rodape">
          <button className={`botao-config ${pagina === "config" ? "ativo" : ""}`} aria-label="Configurações" title="Configurações"
                  onClick={() => ir("config")}>
            <Settings size={18} />
            {estado && estado.rascunho_plano > 0 && <span className="selo selo-aviso">{estado.rascunho_plano}</span>}
          </button>
          {estado && <span className="lateral-empresa"><strong>{estado.empresa}</strong><span>Fechamento {estado.ano}</span></span>}
        </div>
      </aside>
      <main className="conteudo">
        {estado?.planilha_aberta && (
          <div className="faixa-alerta"><TriangleAlert size={16} /> {estado.planilha_aberta}</div>
        )}
        {pagina === "painel" && <Painel estado={estado} ir={ir} />}
        {pagina === "importar" && <Importar contas={contas} aoGravar={atualizar} />}
        {pagina === "caixa" && <ColarCaixa contas={contas} aoGravar={atualizar} />}
        {pagina === "pagar" && <ContasPagar />}
        {pagina === "malote" && <Malote />}
        {pagina === "cartao" && <FaturaCartao contas={contas} aoGravar={atualizar} />}
        {pagina === "fluxo" && <FluxoCaixa />}
        {pagina === "lancamentos" && <Lancamentos contas={contas} bancos={bancos} aoMudar={atualizar} />}
        {pagina === "config" && <Configuracoes secao={rota.secao} ir={(s) => ir("config", s)} contas={contas} bancos={bancos} aoMudar={atualizar} />}
      </main>
      <ListaContas contas={contas} />
    </div>
  );
}
