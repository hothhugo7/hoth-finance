export class ErroApi extends Error {}

async function req<T>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
  const r = await fetch(caminho, { cache: "no-store", ...opcoes });
  if (!r.ok) {
    let msg = `Erro ${r.status}`;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* resposta sem JSON */
    }
    throw new ErroApi(msg);
  }
  return r.json() as Promise<T>;
}

const json = (body: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export interface Estado {
  empresa: string;
  ano: number;
  planilha: string;
  planilha_aberta: string;
  lancamentos: number;
  pendentes: number;
  pendentes_valor: number;
  bancos: { banco: string; lancamentos: number; ultima_data: string | null }[];
  ultima_importacao: [string, string, string, number, string, string] | null;
  backups: number;
  rascunho_plano: number;
}

export interface Sugestao {
  conta: string;
  motivo: string;
}

export interface Novo {
  id: string;
  data: string;
  descricao: string;
  valor: number;
  proposta: string;
  regra: string;
  confianca: string;
  favorecido: string;
  comprovante: string;
  cpf_cnpj: string;
  sugestoes: Sugestao[];
  candidatos: string[];
}

export interface Previa {
  token: string;
  banco: string;
  arquivo: string;
  lidos: number;
  ja_existem: number;
  saldos: { banco: string; ano: number; mes: number; saldo: number }[];
  comprovantes_nao_lidos: string[];
  novos: Novo[];
}

export interface ResultadoGravacao {
  detalhe: string;
  gravados: number;
  duplicados_ignorados: number;
  saldos: string[];
  backup: string | null;
}

export interface LinhaCaixa {
  linha: number;
  data: string | null;
  descricao: string;
  plano_original: string;
  conta: string;
  valor: number;
  avisos: string[];
  loterica: boolean;
  id: string;
  ja_existe: boolean;
  fora_periodo: boolean;
  correcao_de: string;
  incluir: boolean;
}

export interface Titulo {
  id: string;
  codigo: string;
  fornecedor: string;
  documento: string;
  parcela: string | number;
  duplicata: string;
  compra: string | null;
  vencimento: string;
  valor: number;
  banco_ret: string;
  conta: string;
  no_ret: string;
  marca: string;
  observacao: string;
  historico: string;
  situacao: string;
  situacao_texto: string;
  prova: string;
  data_pagamento: string | null;
  valor_pago: number | null;
  banco_pagamento: string;
  descricao_pagamento: string;
  id_lancamento: string;
  malote: string;
  candidatos: { id: string; data: string; banco: string; descricao: string }[];
}

export interface ResumoSituacao { situacao: string; texto: string; quantidade: number; valor: number }

export interface ListaTitulos {
  arquivo: string;
  existe: boolean;
  resumo: ResumoSituacao[];
  total: number;
  soma: number;
  itens: Titulo[];
  ultima_importacao: { quando: string; detalhe: string } | null;
}

export interface PreviaRet {
  token: string;
  arquivo: string;
  lidos: number;
  total: number;
  de: string;
  ate: string;
  novos: number;
  valor_novos: number;
  mudaram: { fornecedor: string; documento: string; vencimento: string; valor: number; valor_antes: number; vencimento_antes: string }[];
  sairam: { fornecedor: string; documento: string; vencimento: string; valor: number }[];
}

export interface CandidatoMalote {
  id: string;
  fornecedor: string;
  documento: string;
  parcela: string | number;
  vencimento: string;
  valor: number;
  situacao_texto: string;
  outro_malote: string;
}

export interface Malote {
  id: string;
  envio: string;
  total_fita: number | null;
  observacao: string;
  quantidade: number;
  soma: number;
  pendentes: number;
  valor_pendente: number;
  dias: number | null;
  valores: { valor: number; titulo: string; observacao: string; fornecedor: string; vencimento: string | null;
    documento: string; parcela: string | number; situacao_texto: string; voltou: boolean; data_pagamento: string | null }[];
}

export interface FornecedorCategoria {
  codigo: string;
  fornecedor: string;
  categoria: string;
  origem: "" | "base" | "voce";
  titulos: number;
  em_aberto: number;
  sugestao: string;
  conta: string;
}

export interface ListaCategorias {
  categorias: string[];
  fornecedores: FornecedorCategoria[];
  pendentes: number;
  da_versao_base: number;
}

export interface DiaFluxo {
  data: string;
  dia: string;
  entradas: number;
  saidas_categoria: Record<string, number>;
  saidas: number;
  resultado: number;
  acumulado: number;
  tipo: "realizado" | "hoje" | "projetado";
}

export interface EntradaFluxo { id: string; data: string; descricao: string; valor: number; forma: string }

export interface Fluxo {
  de: string;
  ate: string;
  categorias: string[];
  dias: DiaFluxo[];
  totais: { entradas: number; saidas: number; resultado: number; por_categoria: Record<string, number> };
  menor_acumulado: { data: string; valor: number } | null;
  meses: { rotulo: string; entradas: number; saidas: number; resultado: number; por_categoria: Record<string, number> }[];
  titulos: { id: string; data: string; valor: number; tipo: string; situacao: string; categoria: string; fornecedor: string; documento: string; vencimento: string }[];
  sem_categoria: number;
  entradas_lancadas: EntradaFluxo[];
  sugestao: { semanas: number; media_diaria: number; por_dia_semana: Record<string, number> };
  planilha: string;
  planilha_existe: boolean;
  aviso_planilha: string;
}

export interface UltimoCaixa {
  ultima_data: string | null;
  ultima_colagem: string | null;
  linhas: { data: string; descricao: string; valor: number; conta: string }[];
}

export interface Regra {
  tipo: "fornecedor" | "descricao";
  chave: string;
  nome: string;
  conta: string;
}

export interface Aprendido {
  banco: string;
  descricao: string;
  sentido: "entrada" | "saída";
  vezes: number;
  conta: string;
  consistencia: number;
  outras: { conta: string; vezes: number }[];
  regra: string | null;
}

export interface Aprendizado {
  regras: Regra[];
  aprendidos: Aprendido[];
  total: number;
  arquivo_regras: string;
}

export interface FaturaArquivo {
  arquivo: string;
  nome: string;
  pasta: string;
  vencimento: string;
  total: number;
  itens: number;
  confere: boolean;
  situacao: "pronta" | "sem_debito" | "varios_debitos" | "aberta" | "aberta_mao";
  aberta_em: string | null;
  aberta_mao: string | null;
  debito: { data: string; valor: number } | null;
}

export interface FaturaAberta {
  id: string; vencimento: string; total: number; data_debito: string; itens: number; situacao: string; aberta_em: string; arquivo: string;
}

export interface ListaFaturas {
  faturas: FaturaArquivo[];
  debitos_sem_pdf: { data: string; valor: number; descricao: string }[];
  ignoradas: number;
  pasta: string;
  abertas: FaturaAberta[];
}

export interface ItemFatura {
  id: string; data_compra: string; descricao: string; valor: number; texto_fatura: string;
  proposta: string; regra: string; confianca: string; sugestoes: string[];
}

export interface PreviaFatura {
  token: string;
  arquivo: string;
  vencimento: string;
  total: number;
  cartao: string;
  agrupada: boolean;
  debito: { data: string; valor: number; descricao: string; conta: string } | null;
  aviso: string;
  itens: ItemFatura[];
}

export interface Lancamento {
  id: string;
  banco: string;
  data: string;
  descricao: string;
  valor: number;
  conta: string;
  grupo: string;
  origem: string;
  observacao: string;
}

export interface GrupoPlano {
  codigo: string;
  nome: string;
  natureza: string;
  entra_dre: boolean;
  entra_dfc: boolean;
  resultado_apos: string;
  base_percentual: boolean;
}

export interface ContaPlano {
  codigo: string;
  nome: string;
  grupo: string;
  grupo_nome: string;
  grupo_dre: string;
  entra_dfc: boolean;
  entra_dre: boolean;
  dre_manual: boolean;
  fixo_variavel: string;
  ativa: boolean;
  observacao: string;
  uso: number;
}

export interface Plano {
  grupos: GrupoPlano[];
  contas: ContaPlano[];
  rascunho: Record<string, unknown>[];
  renomeacoes: Record<string, string>;
}

export interface Versoes {
  backups: { arquivo: string; tamanho: number; data: string }[];
  auditoria: [string, string, string, number, string, string][];
}

export const api = {
  estado: () => req<Estado>("/api/estado"),
  contas: () => req<string[]>("/api/contas"),
  previa: (arquivo: File) => {
    const f = new FormData();
    f.append("arquivo", arquivo);
    return req<Previa>("/api/importacao/previa", { method: "POST", body: f });
  },
  gravar: (token: string, escolhas: Record<string, string>) =>
    req<ResultadoGravacao>("/api/importacao/gravar", json({ token, escolhas })),
  caixaInterpretar: (texto: string, desde: string) =>
    req<{ linhas: LinhaCaixa[] }>("/api/caixa/interpretar", json({ texto, desde: desde || null })),
  caixaGravar: (linhas: LinhaCaixa[]) =>
    req<{ gravados: number; duplicados_ignorados: number; detalhe: string; backup: string | null }>(
      "/api/caixa/gravar", json({ linhas })),
  cpTitulos: (p: Record<string, string>) =>
    req<ListaTitulos>(`/api/cp/titulos?${new URLSearchParams(Object.entries(p).filter(([, v]) => v))}`),
  cpPrevia: (arquivo: File) => {
    const f = new FormData();
    f.append("arquivo", arquivo);
    return req<PreviaRet>("/api/cp/previa", { method: "POST", body: f });
  },
  cpImportar: (token: string) => req<{ detalhe: string; backup: string | null }>("/api/cp/importar", json({ token })),
  cpMarcar: (ids: string[], marca: string, observacao = "", lancamento = "") =>
    req<{ alterados: number }>("/api/cp/marcar", json({ ids, marca, observacao, lancamento })),
  cpCandidatos: (valor: number, envio: string, escolhidos: string[], malote = "") =>
    req<CandidatoMalote[]>("/api/cp/malote/candidatos", json({ valor, envio, escolhidos, malote })),
  cpSalvarMalote: (envio: string, total_fita: number | null, observacao: string,
                   valores: { valor: number; titulo: string; observacao: string }[]) =>
    req<{ id: string; detalhe: string }>("/api/cp/malote", json({ envio, total_fita, observacao, valores })),
  cpEditarMalote: (id: string, envio: string, total_fita: number | null, observacao: string,
                   valores: { valor: number; titulo: string; observacao: string }[]) =>
    req<{ id: string; detalhe: string }>("/api/cp/malote/editar", json({ id, envio, total_fita, observacao, valores, conferido: true })),
  cpExcluirMalote: (id: string) => req<{ detalhe: string }>("/api/cp/malote/excluir", json({ id, conferido: true })),
  cpMalotes: () => req<Malote[]>("/api/cp/malotes"),
  cpCategorias: () => req<ListaCategorias>("/api/cp/categorias"),
  cpSalvarCategorias: (itens: { codigo: string; fornecedor: string; categoria: string }[], nova = "") =>
    req<{ detalhe: string; aviso_fluxo: string }>("/api/cp/categorias", json({ itens, nova })),
  fluxo: (de: string, ate: string) => req<Fluxo>(`/api/fluxo?de=${de}&ate=${ate}`),
  fluxoEntradas: (incluir: { data: string; descricao: string; valor: number; forma: string; repetir_ate: string | null }[],
                  remover: string[] = []) =>
    req<{ detalhe: string; aviso_fluxo: string }>("/api/fluxo/entradas", json({ incluir, remover })),
  fluxoPlanilha: () => req<{ detalhe: string }>("/api/fluxo/planilha", { method: "POST" }),
  caixaUltimo: () => req<UltimoCaixa>("/api/caixa/ultimo"),
  abrirPlanilha: (qual: "oficial" | "fluxo") => req<{ detalhe: string }>("/api/abrir", json({ qual })),
  aprendizado: (busca: string, banco: string, sentido: string) =>
    req<Aprendizado>(`/api/aprendizado?${new URLSearchParams({ busca, banco, sentido })}`),
  salvarRegra: (tipo: string, chave: string, nome: string, conta: string | null) =>
    req<{ detalhe: string }>("/api/aprendizado/regra", json({ tipo, chave, nome, conta })),
  faturas: () => req<ListaFaturas>("/api/fatura/lista"),
  faturaPrevia: (arquivo: string, agrupar: boolean) => req<PreviaFatura>("/api/fatura/previa", json({ arquivo, agrupar })),
  faturaEnviar: (arquivo: File) => {
    const f = new FormData();
    f.append("arquivo", arquivo);
    return req<PreviaFatura>("/api/fatura/enviar", { method: "POST", body: f });
  },
  faturaGravar: (token: string, escolhas: Record<string, string>) =>
    req<{ detalhe: string; backup: string; aviso_fluxo: string }>("/api/fatura/gravar", json({ token, escolhas })),
  faturaDesfazer: (id: string) => req<{ detalhe: string; backup: string }>("/api/fatura/desfazer", json({ id })),
  lancamentos: (p: Record<string, string | number | boolean>) => {
    const q = new URLSearchParams(Object.entries(p).filter(([, v]) => v !== "" && v !== 0 && v !== false)
      .map(([k, v]) => [k, String(v)]));
    return req<{ total: number; soma: number; itens: Lancamento[] }>(`/api/lancamentos?${q}`);
  },
  reclassificar: (ids: string[], conta: string) =>
    req<{ alterados: number; backup: string }>("/api/lancamentos/reclassificar", json({ ids, conta })),
  plano: () => req<Plano>("/api/plano"),
  operacao: (op: Record<string, unknown>) => req<Plano>("/api/plano/operacao", json(op)),
  descartar: () => req<Plano>("/api/plano/rascunho", { method: "DELETE" }),
  aplicarPlano: () => req<{ backup: string; detalhe: string }>("/api/plano/aplicar", { method: "POST" }),
  versoes: () => req<Versoes>("/api/versoes"),
  restaurar: (arquivo: string) => req<{ backup: string }>("/api/versoes/restaurar", json({ arquivo })),
};

const brl = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const dinheiro = (v: number) => brl.format(v);
export const dataBR = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const [d, h] = iso.split("T");
  const [a, m, dia] = d.split("-");
  return `${dia}/${m}/${a}${h ? " " + h.slice(0, 5) : ""}`;
};
/** "1.394,71", "R$ 1394,71" ou "1394.71" -> 1394.71; texto que não é valor -> null. */
export const valorBR = (texto: string): number | null => {
  let t = texto.replace(/R\$|\s/g, "");
  if (!t) return null;
  if (t.includes(",")) t = t.replace(/\./g, "").replace(",", ".");
  else if (/^\d{1,3}(\.\d{3})+$/.test(t)) t = t.replace(/\./g, "");
  return /^-?\d+(\.\d{1,2})?$/.test(t) ? Number(t) : null;
};
export const semAcento =(s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase().trim();
