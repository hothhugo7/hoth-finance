(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const brl = (v) => v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const dataBR = (d) => d.toLocaleDateString("pt-BR");
  const ANO = 2026, MES = 9; // outubro (0 = janeiro)
  const HOJE = new Date(ANO, MES, 30);

  /* ---------------- plano de contas ---------------- */
  const PLANO = [
    ["RECEITA DE VENDAS DE MERCADORIA", "Receita"], ["DAS - SIMPLES NACIONAL", "Impostos"],
    ["FORNECEDOR EM GERAL", "CPV"], ["FORNECEDOR DA PADARIA", "CPV"], ["FORNECEDOR DE LATICINIOS", "CPV"],
    ["FORNECEDOR DE AÇOUGUE", "CPV"], ["FORNECEDOR DE BEBIDAS", "CPV"], ["FORNECEDOR DE HORTIFRUTI", "CPV"],
    ["ALUGUEL IMÓVEL", "Administrativas"], ["ENERGIA ELÉTRICA", "Administrativas"], ["ÁGUA E ESGOTO", "Administrativas"],
    ["CONTABILIDADE", "Administrativas"], ["INTERNET E DADOS", "Administrativas"], ["MATERIAL DE ESCRITÓRIO", "Administrativas"],
    ["MANUTENÇÃO PREDIAL E LIMPEZA", "Administrativas"], ["COMBUSTIVEL E PEDAGIO", "Administrativas"],
    ["SALÁRIOS (CLT)", "Pessoal"], ["FGTS (CLT)", "Pessoal"], ["FREELANCE (PESSOAL)", "Pessoal"], ["PROLABORE SÓCIO A", "Pessoal"],
    ["DESPESAS BANCÁRIAS", "Financeiras"], ["TRANSFERÊNCIA ENTRE CONTAS", "Movimentação"],
  ];
  const GRUPO = Object.fromEntries(PLANO);
  const FORN = [
    ["00101", "DISTRIBUIDORA ALFA LTDA", "FORNECEDOR EM GERAL", 12600, 6], ["00102", "PANIFICADORA BOM GRAO", "FORNECEDOR DA PADARIA", 3900, 5],
    ["00103", "LATICINIOS SERRA AZUL", "FORNECEDOR DE LATICINIOS", 7800, 5], ["00104", "FRIGORIFICO VALE VERDE", "FORNECEDOR DE AÇOUGUE", 15300, 5],
    ["00105", "BEBIDAS RIO CLARO", "FORNECEDOR DE BEBIDAS", 11400, 4], ["00106", "HORTIFRUTI DO CAMPO", "FORNECEDOR DE HORTIFRUTI", 5100, 7],
  ];
  const REGRAS = [ // regras fixas: o que o app já sabe antes de você usar
    [/CARTOES|ADQUIRENTE/, "RECEITA DE VENDAS DE MERCADORIA"], [/PIX RECEBIDO/, "RECEITA DE VENDAS DE MERCADORIA"],
    [/ALUGUEL/, "ALUGUEL IMÓVEL"], [/ENERGIA/, "ENERGIA ELÉTRICA"], [/SANEAMENTO|AGUA/, "ÁGUA E ESGOTO"],
    [/CONTABIL/, "CONTABILIDADE"], [/FIBRA|INTERNET/, "INTERNET E DADOS"], [/FOLHA/, "SALÁRIOS (CLT)"], [/FGTS/, "FGTS (CLT)"],
    [/SIMPLES NACIONAL|DAS /, "DAS - SIMPLES NACIONAL"], [/TARIFA/, "DESPESAS BANCÁRIAS"], [/PROLABORE/, "PROLABORE SÓCIO A"],
    [/APLICACAO|TRANSF ENTRE/, "TRANSFERÊNCIA ENTRE CONTAS"],
  ];

  /* ---------------- geração dos dados fictícios ---------------- */
  let semente = Date.now() % 100000;
  const rnd = () => { semente = (semente * 16807) % 2147483647; return (semente - 1) / 2147483646; };
  const entre = (a, b) => a + rnd() * (b - a);
  const inteiro = (a, b) => Math.floor(entre(a, b + 1));
  const PESO = [0.9, 0.92, 0.85, 0.88, 0.95, 1.12, 1.38]; // dom..sáb
  let extrato = [], titulos = [];

  function gerar() {
    extrato = []; titulos = [];
    const add = (dia, desc, doc, valor) => extrato.push({ data: new Date(ANO, MES, dia), desc, doc, valor: Math.round(valor * 100) / 100 });
    for (let d = 1; d <= 30; d++) {
      const w = new Date(ANO, MES, d).getDay(), venda = 19500 * PESO[w] * entre(.9, 1.1);
      add(d, "RECEBIMENTO CARTOES ADQUIRENTE", "", venda * .7);
      if (d % 2) add(d, "PIX RECEBIDO VENDAS BALCAO", "", venda * .12);
    }
    for (const [cod, nome, , media, vezes] of FORN) for (let i = 0; i < vezes; i++) {
      const dia = inteiro(1, 29), valor = Math.round(media * entre(.7, 1.3) * 100) / 100, doc = String(inteiro(100000, 999999));
      const venc = new Date(ANO, MES, dia), sorte = rnd();
      if (sorte < .62) { add(dia, `PAGTO BOLETO ${cod} ${nome}`, doc, -valor); titulos.push({ cod, nome, doc, venc, valor }); }
      else if (sorte < .78) { add(dia, `PAGTO BOLETO ${cod} ${nome}`, "", -valor); titulos.push({ cod, nome, doc, venc, valor }); }
      else if (sorte < .88) { add(dia, "PAGAMENTO DE TITULO", "", -valor); titulos.push({ cod, nome, doc, venc, valor }); }
      else titulos.push({ cod, nome, doc, venc, valor }); // não pago: vencido
    }
    for (const [cod, nome, , media] of FORN) for (let i = 0; i < 3; i++)
      titulos.push({ cod, nome, doc: String(inteiro(100000, 999999)), venc: new Date(ANO, MES, 31 + inteiro(0, 28)), valor: Math.round(media * entre(.7, 1.3) * 100) / 100 });
    add(5, "ALUGUEL IMOBILIARIA EXEMPLO", "", -9500); add(12, "ENERGIA ELETRICA CONCESSIONARIA", "", -entre(6800, 7600));
    add(15, "AGUA SANEAMENTO MUNICIPAL", "", -entre(900, 1100)); add(10, "CONTABILIDADE EXEMPLO", "", -1800);
    add(20, "INTERNET FIBRA EMPRESARIAL", "", -320); add(5, "FOLHA DE PAGAMENTO", "", -48000); add(7, "FGTS GRRF", "", -3900);
    add(20, "DAS SIMPLES NACIONAL", "", -21000); add(5, "PROLABORE SOCIO A", "", -6000); add(1, "TARIFA PACOTE DE SERVICOS", "", -189);
    add(25, "APLICACAO CDB", "", -15000);
    // o que o app ainda não conhece: precisa de você (e aprende)
    for (const d of [4, 11, 18, 25]) add(d, "PIX ENVIADO JOAO PEREIRA DIARISTA", "", -entre(160, 220));
    for (const d of [8, 22]) add(d, "COMPRA DEBITO PAPELARIA CENTRAL", "", -entre(80, 260));
    for (const d of [9, 23]) add(d, "COMPRA DEBITO POSTO BOA ESTRADA", "", -entre(180, 320));
    add(17, "PIX ENVIADO REFRIGERACAO POLAR MANUTENCAO", "", -entre(600, 900));
    add(26, "PIX ENVIADO REFRIGERACAO POLAR", "", -entre(300, 500));
    extrato.sort((a, b) => a.data - b.data);
    $("#infoExtrato").textContent = `${extrato.length} linhas · outubro/2026 · gerado agora`;
    $("#infoTitulos").textContent = `${titulos.length} boletos · ${FORN.length} fornecedores`;
  }

  const csvExtrato = () => "Data;Histórico;Documento;Valor\n" + extrato.map((l) => `${dataBR(l.data)};${l.desc};${l.doc};${brl(l.valor).replace(/\./g, "")}`).join("\n");
  const csvTitulos = () => "Código;Fornecedor;Documento;Vencimento;Valor\n" + titulos.map((t) => `${t.cod};${t.nome};${t.doc};${dataBR(t.venc)};${brl(t.valor).replace(/\./g, "")}`).join("\n");
  function baixar(nome, texto) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + texto], { type: "text/csv;charset=utf-8" }));
    a.download = nome; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  const lerData = (s) => { const [d, m, a] = s.split("/").map(Number); return new Date(a, m - 1, d); };
  const lerValor = (s) => Number(String(s).replace(/\./g, "").replace(",", "."));
  function lerCsv(texto) {
    const linhas = texto.replace(/^﻿/, "").trim().split(/\r?\n/).map((l) => l.split(";"));
    return { cab: linhas[0].map((c) => c.trim().toLowerCase()), linhas: linhas.slice(1).filter((l) => l.length > 3) };
  }

  /* ---------------- classificador ---------------- */
  const aprendido = new Map();
  const chave = (d) => d.toUpperCase().replace(/[0-9]/g, "").replace(/\s+/g, " ").trim();
  const palavras = (d) => new Set(chave(d).split(" ").filter((p) => p.length >= 4 && !["PAGTO", "BOLETO", "ENVIADO", "COMPRA", "DEBITO"].includes(p)));
  function parecido(a, b) {
    const A = palavras(a), B = palavras(b); if (!A.size || !B.size) return 0;
    let c = 0; A.forEach((p) => B.has(p) && c++); return c / Math.min(A.size, B.size);
  }
  function classificar(l) {
    const desc = l.desc.toUpperCase();
    if (aprendido.has(chave(desc))) return { conta: aprendido.get(chave(desc)), conf: 96, motivo: "aprendido com você" };
    const f = FORN.find(([cod]) => desc.includes(cod));
    if (f) return { conta: f[2], conf: 98, motivo: `fornecedor ${f[0]}` };
    for (const [re, conta] of REGRAS) if (re.test(desc)) return { conta, conf: 99, motivo: "regra fixa" };
    let melhor = null;
    for (const [k, conta] of aprendido) { const s = parecido(desc, k); if (s >= .5 && (!melhor || s > melhor.s)) melhor = { s, conta }; }
    if (melhor) return { conta: melhor.conta, conf: Math.round(70 + melhor.s * 22), motivo: "parecido com o que você ensinou" };
    if (desc === "PAGAMENTO DE TITULO") return { conta: "FORNECEDOR EM GERAL", conf: 62, motivo: "sugestão pelo histórico" };
    return { conta: "", conf: 0, motivo: "desconhecido" };
  }

  /* ---------------- estado e navegação ---------------- */
  let lancs = [], filtro = "revisar", aprendidosAgora = 0, conciliado = null, gravado = false, titulosImportados = false;
  const PASSOS = [
    ["Baixe os arquivos", "Os dois arquivos foram gerados agora com dados fictícios. Baixe o extrato (e, se quiser, as contas em aberto) e clique em Começar."],
    ["Importe o extrato", "Arraste o extrato_santander_outubro.csv para a área tracejada. O app lê, confere duplicidades e classifica cada linha."],
    ["Ensine o que ele não sabe", "As linhas amarelas precisam de você. Escolha a conta: o app aprende e aplica sozinho às linhas parecidas. Depois, grave."],
    ["Concilie as contas a pagar", "Importe contas_em_aberto.csv (ou use as já geradas) e clique em Conciliar. Cada boleto é procurado no extrato."],
    ["Veja o resultado", "DRE e fluxo prontos. Volte ao passo 2, troque uma conta e veja os números mudarem."],
  ];
  const TELAS = ["inicio", "importar", "classificar", "pagar", "resultado"];
  let etapa = 0;
  function guia(n) {
    etapa = Math.max(etapa, n);
    $("#guiaTitulo").textContent = PASSOS[n][0]; $("#guiaTexto").textContent = PASSOS[n][1];
    $("#guiaBarra").style.width = (n / (PASSOS.length - 1)) * 100 + "%";
    $("#guiaLista").innerHTML = PASSOS.map(([t], k) => `<li class="${k < etapa ? "feito" : k === n ? "atual" : ""}">${t}</li>`).join("");
  }
  function ir(tela) {
    const n = TELAS.indexOf(tela);
    $$(".tela").forEach((t) => t.classList.toggle("ativa", t.id === "tela-" + tela));
    $$("#menu button").forEach((b) => b.classList.toggle("ativo", b.dataset.tela === tela));
    $(".conteudo").scrollTop = 0; guia(n);
    $$(".chamar").forEach((e) => e.classList.remove("chamar"));
    const alvo = { inicio: "#irImportar", importar: "#soltar", classificar: "#gravar", pagar: conciliado ? "#verResultado" : "#conciliar", resultado: "#recomecar" }[tela];
    $(alvo).classList.add("chamar");
    if (tela === "resultado") resultado();
  }
  function liberar(tela) { const b = $(`#menu [data-tela="${tela}"]`); b.disabled = false; }
  function marcar(tela) { $(`#menu [data-tela="${tela}"]`).classList.add("feito"); }
  $$("#menu button").forEach((b) => b.addEventListener("click", () => ir(b.dataset.tela)));
  let tt; function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("on"); clearTimeout(tt); tt = setTimeout(() => t.classList.remove("on"), 2600); }

  /* ---------------- passo 1: importar ---------------- */
  $$("[data-baixar]").forEach((b) => b.addEventListener("click", () => {
    b.dataset.baixar === "extrato" ? baixar("extrato_santander_outubro.csv", csvExtrato()) : baixar("contas_em_aberto.csv", csvTitulos());
    b.textContent = "Baixado ✓";
  }));
  $("#irImportar").addEventListener("click", () => { liberar("importar"); ir("importar"); });
  $("#novosDados").addEventListener("click", () => { gerar(); $$("[data-baixar]").forEach((b) => (b.textContent = "Baixar")); toast("Novos dados fictícios gerados"); });

  const soltar = $("#soltar");
  ["dragenter", "dragover"].forEach((ev) => soltar.addEventListener(ev, (e) => { e.preventDefault(); soltar.classList.add("sobre"); }));
  ["dragleave", "drop"].forEach((ev) => soltar.addEventListener(ev, (e) => { e.preventDefault(); soltar.classList.remove("sobre"); }));
  soltar.addEventListener("drop", (e) => e.dataTransfer.files[0] && lerArquivo(e.dataTransfer.files[0]));
  $("#arquivoExtrato").addEventListener("change", (e) => e.target.files[0] && lerArquivo(e.target.files[0]));
  $("#usarExemplo").addEventListener("click", () => importar(csvExtrato(), "extrato de exemplo"));
  function lerArquivo(f) { const r = new FileReader(); r.onload = () => importar(r.result, f.name); r.readAsText(f, "utf-8"); }

  function importar(texto, nome) {
    const { cab, linhas } = lerCsv(texto);
    const log = $("#logImport"); log.innerHTML = "";
    if (!cab.includes("histórico") && !cab.includes("historico")) { log.innerHTML = `<div class="neg">Este arquivo não parece um extrato. Use o extrato_santander_outubro.csv.</div>`; return; }
    const barra = $("#leitura i"); barra.style.width = "0";
    const linhasLog = [
      `→ Lendo ${nome}`, `→ Formato reconhecido: Santander (CSV)`, `→ ${linhas.length} linhas · período 01/10 a 30/10/2026`,
      `→ 0 duplicadas (nada importado antes)`, `→ Classificando com regras fixas, fornecedores e histórico…`,
    ];
    linhasLog.forEach((t, k) => setTimeout(() => { log.insertAdjacentHTML("beforeend", `<div>${t}</div>`); barra.style.width = ((k + 1) / (linhasLog.length + 1)) * 100 + "%"; }, k * 380));
    setTimeout(() => {
      lancs = linhas.map(([d, desc, doc, v], i) => ({ id: i, data: lerData(d), desc: desc.trim(), doc: (doc || "").trim(), valor: lerValor(v), ...classificar({ desc }), confirmado: false }));
      lancs.forEach((l) => { l.confirmado = l.conf >= 90; });
      barra.style.width = "100%";
      const auto = lancs.filter((l) => l.confirmado).length;
      log.insertAdjacentHTML("beforeend", `<div class="ok">✓ ${auto} de ${lancs.length} classificados sozinhos (${Math.round(auto / lancs.length * 100)}%)</div>`);
      gravado = false; conciliado = null; aprendidosAgora = 0;
      setTimeout(() => { liberar("classificar"); marcar("importar"); ir("classificar"); desenharTabela(true); }, 900);
    }, linhasLog.length * 380 + 300);
  }

  /* ---------------- passo 2: classificar ---------------- */
  const opcoes = (sel) => `<option value="">Escolha a conta…</option>` + PLANO.map(([c]) => `<option ${c === sel ? "selected" : ""}>${c}</option>`).join("");
  function metricas() {
    const rev = lancs.filter((l) => !l.confirmado).length;
    const set = (id, v) => { const el = $(id); if (el.textContent !== String(v)) { el.textContent = v; el.classList.remove("pulsar"); void el.offsetWidth; el.classList.add("pulsar"); } };
    set("#mTotal", lancs.length); set("#mAuto", lancs.length - rev - aprendidosAgora); set("#mRevisar", rev); set("#mAprendidos", aprendidosAgora);
    const g = $("#gravar"); g.disabled = rev > 0; g.textContent = rev ? `Faltam ${rev} para gravar` : gravado ? "Gravado ✓ — conciliar →" : "Gravar na planilha";
  }
  function desenharTabela(entrada, brilhos = new Set()) {
    const lista = filtro === "revisar" ? lancs.filter((l) => !l.confirmado || brilhos.has(l.id)) : lancs;
    const tb = $("#tabela tbody");
    tb.innerHTML = lista.length ? lista.map((l, k) => {
      const cor = l.confirmado ? "var(--ok)" : l.conf ? "var(--alerta)" : "var(--erro)";
      return `<tr data-id="${l.id}" class="${entrada ? "entra" : ""} ${brilhos.has(l.id) ? "brilho" : ""}" style="animation-delay:${entrada ? Math.min(k, 20) * 25 : 0}ms">
        <td class="mono">${dataBR(l.data).slice(0, 5)}</td><td>${l.desc}</td>
        <td class="num ${l.valor < 0 ? "neg" : "pos"}">${brl(l.valor)}</td>
        <td><select class="${l.confirmado ? "" : "al"}">${opcoes(l.conta)}</select></td>
        <td><span class="conf" title="${l.motivo}"><i style="--p:${l.confirmado ? 100 : l.conf}%;--cor:${cor}"></i>${l.confirmado ? (l.motivo === "aprendido com você" || l.motivo === "confirmado por você" ? l.motivo : l.conf + "%") : l.conf ? "sugestão" : "revisar"}</span>
          ${!l.confirmado && l.conta ? `<button class="filtro confirmar" style="margin-left:6px">✓</button>` : ""}</td></tr>`;
    }).join("") : `<tr><td colspan="5" class="vazio">Tudo classificado. Clique em <b>Gravar na planilha</b>.</td></tr>`;
    metricas();
  }
  function ensinar(l, conta) {
    const novo = !aprendido.has(chave(l.desc));
    aprendido.set(chave(l.desc), conta);
    l.conta = conta; l.conf = 96; l.motivo = "confirmado por você";
    if (!l.confirmado) { l.confirmado = true; aprendidosAgora++; }
    const brilhos = new Set([l.id]);
    let n = 0;
    for (const o of lancs) if (!o.confirmado) {
      const c = classificar(o);
      if (c.conf >= 90) { Object.assign(o, c, { confirmado: true }); brilhos.add(o.id); n++; aprendidosAgora++; }
      else if (c.conf > o.conf) { Object.assign(o, c); brilhos.add(o.id); }
    }
    if (n) toast(`Aprendido! Apliquei "${conta}" a mais ${n} ${n > 1 ? "lançamentos parecidos" : "lançamento parecido"}.`);
    else if (novo) toast("Aprendido. Da próxima vez, ele classifica sozinho.");
    gravado = false; desenharTabela(false, brilhos);
  }
  $("#tabela").addEventListener("change", (e) => {
    if (e.target.tagName !== "SELECT" || !e.target.value) return;
    const l = lancs[+e.target.closest("tr").dataset.id]; ensinar(l, e.target.value);
  });
  $("#tabela").addEventListener("click", (e) => {
    if (!e.target.classList.contains("confirmar")) return;
    const l = lancs[+e.target.closest("tr").dataset.id]; ensinar(l, l.conta);
  });
  $$(".filtro[data-filtro]").forEach((b) => b.addEventListener("click", () => {
    filtro = b.dataset.filtro; $$(".filtro[data-filtro]").forEach((x) => x.classList.toggle("ativo", x === b)); desenharTabela(true);
  }));
  $("#gravar").addEventListener("click", () => {
    if (gravado) return ir("pagar");
    gravado = true; marcar("classificar"); liberar("pagar"); metricas();
    toast(`${lancs.length} lançamentos gravados · backup feito · auditoria registrada`);
    setTimeout(() => ir("pagar"), 900);
  });

  /* ---------------- passo 3: conciliação ---------------- */
  let carteira = [];
  function usarTitulos(lista) { carteira = lista; titulosImportados = true; desenharPagar(); }
  $("#arquivoTitulos").addEventListener("change", (e) => {
    const f = e.target.files[0]; if (!f) return;
    const r = new FileReader();
    r.onload = () => {
      const { cab, linhas } = lerCsv(r.result);
      if (!cab.includes("fornecedor")) return toast("Este arquivo não é o contas_em_aberto.csv");
      usarTitulos(linhas.map(([cod, nome, doc, venc, v]) => ({ cod, nome, doc, venc: lerData(venc), valor: lerValor(v) })));
      toast(`${carteira.length} boletos importados`); $("#arquivoTitulos").parentElement.classList.remove("chamar"); $("#conciliar").classList.add("chamar");
    };
    r.readAsText(f, "utf-8");
  });
  function conciliar() {
    if (!titulosImportados) usarTitulos(titulos.map((t) => ({ ...t })));
    const usados = new Set(), perto = (a, b) => Math.abs(a - b) <= 5 * 864e5;
    const saidas = lancs.filter((l) => l.valor < 0);
    conciliado = carteira.map((t) => {
      const igual = (l) => !usados.has(l.id) && Math.abs(-l.valor - t.valor) < .01;
      let l = saidas.find((l) => igual(l) && l.desc.includes(t.cod) && l.doc === t.doc), r;
      if (l) r = ["Pago e conferido", "s-ok", `Código + documento: ${l.desc.slice(0, 32)} em ${dataBR(l.data)}`];
      else if ((l = saidas.find((l) => igual(l) && l.desc.includes(t.cod) && perto(l.data, t.venc))))
        r = ["Pago e conferido", "s-ok", `Código + valor em ${dataBR(l.data)}`];
      else if ((l = saidas.find((l) => igual(l) && !/\d{5}/.test(l.desc) && perto(l.data, t.venc))))
        r = ["Pago provável", "s-al", `Só o valor bate: "${l.desc}" em ${dataBR(l.data)} — confirme`];
      else if (t.venc < HOJE) r = ["Vencido", "s-er", "Nenhum pagamento encontrado"];
      else r = ["A vencer", "s-nt", `Vence em ${Math.ceil((t.venc - HOJE) / 864e5)} dias`];
      if (l) usados.add(l.id);
      return { ...t, situacao: r[0], cls: r[1], prova: r[2] };
    }).sort((a, b) => a.venc - b.venc);
    desenharPagar(true);
    marcar("pagar"); liberar("resultado"); $("#verResultado").disabled = false;
    $("#conciliar").classList.remove("chamar"); $("#verResultado").classList.add("chamar");
    toast("Conciliação concluída");
  }
  function desenharPagar(animar) {
    const lista = conciliado || carteira.map((t) => ({ ...t, situacao: "Não conferido", cls: "s-nt", prova: "—" }));
    const conta = (s) => lista.filter((t) => t.situacao === s);
    const soma = (l) => brl(l.reduce((a, t) => a + t.valor, 0));
    $("#metricasPagar").innerHTML = [["Pago e conferido", "ok"], ["Pago provável", "al"], ["Vencido", "er"], ["A vencer", ""]].map(([s, c]) =>
      `<div class="metrica ${c}"><small>${s}</small><b>${conta(s).length}</b><span class="prova">R$ ${soma(conta(s))}</span></div>`).join("");
    $("#tabelaPagar tbody").innerHTML = lista.length ? lista.map((t, k) => `<tr class="${animar ? "entra" : ""}" style="animation-delay:${animar ? Math.min(k, 30) * 35 : 0}ms">
      <td class="mono">${dataBR(t.venc)}</td><td>${t.cod} - ${t.nome}</td><td class="num">${brl(t.valor)}</td>
      <td><span class="status ${t.cls}">${t.situacao}</span></td><td class="prova">${t.prova}</td></tr>`).join("")
      : `<tr><td colspan="5" class="vazio">Importe o contas_em_aberto.csv, ou clique em <b>Conciliar agora</b> para usar os boletos já gerados.</td></tr>`;
  }
  $("#conciliar").addEventListener("click", conciliar);
  $("#verResultado").addEventListener("click", () => ir("resultado"));

  /* ---------------- passo 4: resultado ---------------- */
  function resultado() {
    const g = {}; lancs.forEach((l) => { const k = GRUPO[l.conta] || "Sem conta"; g[k] = (g[k] || 0) + l.valor; });
    const rec = g.Receita || 0, ordem = ["Impostos", "CPV", "Administrativas", "Pessoal", "Financeiras"];
    const res = rec + ordem.reduce((a, k) => a + (g[k] || 0), 0);
    const entradas = lancs.filter((l) => l.valor > 0 && GRUPO[l.conta] !== "Movimentação").reduce((a, l) => a + l.valor, 0);
    const saidas = lancs.filter((l) => l.valor < 0 && GRUPO[l.conta] !== "Movimentação").reduce((a, l) => a + l.valor, 0);
    const abertos = (conciliado || []).filter((t) => t.situacao === "Vencido" || t.situacao === "A vencer");
    $("#kpis").innerHTML = [["Receita", rec, "ok"], ["Saídas", saidas, "er"], ["Resultado", res, res >= 0 ? "ok" : "er"],
      ["A pagar (aberto)", -abertos.reduce((a, t) => a + t.valor, 0), "al"]].map(([n, v, c]) =>
      `<div class="metrica ${c}"><small>${n}</small><b class="cont" data-v="${v}">R$ 0</b></div>`).join("");
    $$("#kpis .cont").forEach((el) => { const alvo = +el.dataset.v, t0 = performance.now();
      const f = (t) => { const p = Math.min(1, (t - t0) / 1200); el.textContent = "R$ " + brl(alvo * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(f); }; requestAnimationFrame(f); });
    const linha = (n, v, total, cor) => `<div class="dre-linha ${total ? "total" : ""}"><span>${n}</span><span class="num ${v < 0 ? "neg" : "pos"}">${brl(v)}</span>
      ${total ? "" : `<div class="barra"><i style="background:${cor}" data-w="${Math.min(100, Math.abs(v) / rec * 100)}"></i></div>`}</div>`;
    $("#dre").innerHTML = linha("Receita de vendas", rec, 0, "var(--ok)") + ordem.map((k) => linha(k === "CPV" ? "CPV (fornecedores)" : k === "Impostos" ? "Impostos" : "Despesas " + k.toLowerCase(), g[k] || 0, 0, "var(--erro)")).join("")
      + linha("Resultado do mês", res, 1) + `<p class="prova" style="margin-top:10px">Margem: ${(res / rec * 100).toFixed(1)}%</p>`;
    requestAnimationFrame(() => $$("#dre .barra i").forEach((i) => (i.style.width = i.dataset.w + "%")));
    grafico(abertos);
  }
  function grafico(abertos) {
    const svg = $("#graficoSaldo"), W = 600, H = 230, ini = 85000;
    const real = [], proj = []; let s = ini;
    for (let d = 1; d <= 30; d++) { s += lancs.filter((l) => l.data.getDate() === d).reduce((a, l) => a + l.valor, 0); real.push(s); }
    const media = lancs.filter((l) => GRUPO[l.conta] === "Receita").reduce((a, l) => a + l.valor, 0) / 30;
    let p = s;
    for (let d = 1; d <= 30; d++) {
      const dia = new Date(ANO, MES, 30 + d);
      const venda = media * PESO[dia.getDay()];  // vendas previstas pelo dia da semana, menos as compras e despesas que elas puxam
      p += venda * 0.25 - abertos.filter((t) => t.venc.toDateString() === dia.toDateString() || (d === 1 && t.venc < HOJE)).reduce((a, t) => a + t.valor, 0);
      proj.push(p);
    }
    const todos = [...real, ...proj], min = Math.min(...todos, 0), max = Math.max(...todos);
    const x = (i) => (i / 59) * W, y = (v) => H - ((v - min) / (max - min || 1)) * (H - 20) - 4;
    const caminho = (arr, off) => arr.map((v, i) => `${i ? "L" : "M"}${x(i + off).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
    const grade = [0, .25, .5, .75, 1].map((f) => { const v = min + (max - min) * f; return `<line class="grade" x1="0" x2="${W}" y1="${y(v)}" y2="${y(v)}"/><text x="2" y="${y(v) - 3}">${Math.round(v / 1000)}k</text>`; }).join("");
    svg.innerHTML = `<defs><linearGradient id="gradSaldo" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#c9cdd2" stop-opacity=".25"/><stop offset="1" stop-color="#c9cdd2" stop-opacity="0"/></linearGradient></defs>
      ${grade}<path class="area" d="${caminho(real, 0)} L${x(29)} ${H} L0 ${H} Z"/>
      <path class="linha desenhar" d="${caminho(real, 0)}"/><path class="proj desenhar" style="animation-delay:1.2s" d="M${x(29)} ${y(real[29])} ${caminho(proj, 30).replace("M", "L")}"/>
      <line x1="${x(29)}" x2="${x(29)}" y1="0" y2="${H}" stroke="rgba(255,255,255,.15)" stroke-dasharray="3 3"/>
      <text x="${x(29) + 4}" y="12">hoje</text><text x="0" y="${H + 16}">01/10</text><text x="${W - 34}" y="${H + 16}">29/11</text>`;
  }
  $("#baixarPlanilha").addEventListener("click", () => baixar("lancamentos_classificados.csv",
    "Data;Descrição;Documento;Valor;Conta;Grupo\n" + lancs.map((l) => `${dataBR(l.data)};${l.desc};${l.doc};${brl(l.valor).replace(/\./g, "")};${l.conta};${GRUPO[l.conta] || ""}`).join("\n")));
  $("#recomecar").addEventListener("click", () => location.reload());

  gerar(); guia(0); $("#irImportar").classList.add("chamar");
})();
