import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { X } from "lucide-react";
import { semAcento } from "../api";

/* ---------------------------------------------------------------- Logo */
export function Logo({ compacto = false }: { compacto?: boolean }) {
  return (
    <div className="logo">
      <svg viewBox="0 0 100 100" className="logo-marca" aria-hidden="true">
        <defs>
          <linearGradient id="prata" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#eef0f3" />
            <stop offset="0.55" stopColor="#a9afb7" />
            <stop offset="1" stopColor="#6d737b" />
          </linearGradient>
        </defs>
        <path d="M18 8 L36 20 L36 50 L64 32 L64 20 L82 8 L82 92 L64 80 L64 52 L36 70 L36 80 L18 92 Z" fill="url(#prata)" />
      </svg>
      {!compacto && (
        <div className="logo-texto">
          <span className="logo-nome">HOTH</span>
          <span className="logo-sub">SOLUTIONS</span>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------- Toasts */
type Aviso = { id: number; tipo: "ok" | "erro" | "info"; texto: string };
const AvisoCtx = createContext<(tipo: Aviso["tipo"], texto: string) => void>(() => {});
export const useAviso = () => useContext(AvisoCtx);

export function Avisos({ children }: { children: ReactNode }) {
  const [lista, setLista] = useState<Aviso[]>([]);
  const avisar = useCallback((tipo: Aviso["tipo"], texto: string) => {
    const id = Date.now() + Math.random();
    setLista((l) => [...l, { id, tipo, texto }]);
    setTimeout(() => setLista((l) => l.filter((a) => a.id !== id)), tipo === "erro" ? 9000 : 5000);
  }, []);
  return (
    <AvisoCtx.Provider value={avisar}>
      {children}
      <div className="avisos" role="status">
        {lista.map((a) => (
          <div key={a.id} className={`aviso aviso-${a.tipo}`}>
            <span>{a.texto}</span>
            <button className="icone" onClick={() => setLista((l) => l.filter((x) => x.id !== a.id))} aria-label="Fechar">
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </AvisoCtx.Provider>
  );
}

/* --------------------------------------------------------------- Modal */
export function Modal({ titulo, children, aoFechar, acoes }: {
  titulo: string; children: ReactNode; aoFechar: () => void; acoes?: ReactNode;
}) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && aoFechar();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [aoFechar]);
  return (
    <div className="modal-fundo" onMouseDown={(e) => e.target === e.currentTarget && aoFechar()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={titulo}>
        <div className="modal-cab">
          <h3>{titulo}</h3>
          <button className="icone" onClick={aoFechar} aria-label="Fechar"><X size={16} /></button>
        </div>
        <div className="modal-corpo">{children}</div>
        {acoes && <div className="modal-acoes">{acoes}</div>}
      </div>
    </div>
  );
}

/* --------------------------------------------------- Campo de conta */
export function ContaInput({ valor, contas, aoMudar, placeholder = "Escolha a conta", autoFocus }: {
  valor: string; contas: string[]; aoMudar: (v: string) => void; placeholder?: string; autoFocus?: boolean;
}) {
  const [texto, setTexto] = useState(valor);
  useEffect(() => setTexto(valor), [valor]);
  const valida = texto === "" || contas.some((c) => semAcento(c) === semAcento(texto));
  const confirmar = (v: string) => {
    const achada = contas.find((c) => semAcento(c) === semAcento(v));
    if (achada !== undefined) aoMudar(achada);
    else if (v === "") aoMudar("");
  };
  return (
    <input
      className={`campo campo-conta ${valida ? "" : "invalido"}`}
      list="lista-contas"
      value={texto}
      placeholder={placeholder}
      autoFocus={autoFocus}
      title={valida ? texto : "Conta não existe no Plano de Contas"}
      onChange={(e) => {
        setTexto(e.target.value);
        if (contas.includes(e.target.value)) aoMudar(e.target.value);
      }}
      onBlur={() => confirmar(texto)}
      onKeyDown={(e) => e.key === "Enter" && confirmar(texto)}
    />
  );
}

export function ListaContas({ contas }: { contas: string[] }) {
  return (
    <datalist id="lista-contas">
      {contas.map((c) => <option key={c} value={c} />)}
    </datalist>
  );
}

export function Carregando({ texto = "Carregando…" }: { texto?: string }) {
  return <div className="carregando"><span className="giro" />{texto}</div>;
}

export function Metrica({ rotulo, valor, detalhe, tom }: {
  rotulo: string; valor: ReactNode; detalhe?: ReactNode; tom?: "alerta" | "ok";
}) {
  return (
    <div className={`metrica ${tom ? "metrica-" + tom : ""}`}>
      <span className="metrica-rotulo">{rotulo}</span>
      <strong className="metrica-valor">{valor}</strong>
      {detalhe && <span className="metrica-detalhe">{detalhe}</span>}
    </div>
  );
}

/* ------------------------------------------------- Campo de data (dd/mm/aaaa) */
// O campo nativo de data segue o idioma do navegador embutido (mês/dia em inglês); este é sempre dia/mês.
const isoParaBR = (iso: string | null) => (iso ? iso.split("-").reverse().join("/") : "");

export function DataInput({ valor, aoMudar, permitirVazio = false }: {
  valor: string | null; aoMudar: (iso: string | null) => void; permitirVazio?: boolean;
}) {
  const [texto, setTexto] = useState(isoParaBR(valor));
  useEffect(() => setTexto(isoParaBR(valor)), [valor]);
  const m = texto.trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/);
  const iso = m ? `${m[3].length === 2 ? "20" + m[3] : m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}` : null;
  const valida = !!iso && !Number.isNaN(Date.parse(iso)) && new Date(iso).toISOString().startsWith(iso);
  const confirmar = () => {
    if (valida) aoMudar(iso);
    else if (!texto.trim() && permitirVazio) aoMudar(null);
    else setTexto(isoParaBR(valor));
  };
  return (
    <input className={`campo campo-data ${valida || !texto ? "" : "invalido"}`} value={texto} placeholder="dd/mm/aaaa"
           inputMode="numeric" onChange={(e) => setTexto(e.target.value)} onBlur={confirmar}
           onKeyDown={(e) => e.key === "Enter" && confirmar()} />
  );
}
