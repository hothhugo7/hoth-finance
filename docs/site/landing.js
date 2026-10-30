(() => {
  const calmo = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  /* ---------- barra de progresso e nav ---------- */
  const barra = $("#progresso"), nav = $("#nav");
  addEventListener("scroll", () => {
    const h = document.documentElement;
    barra.style.width = (h.scrollTop / (h.scrollHeight - h.clientHeight)) * 100 + "%";
    nav.classList.toggle("solida", h.scrollTop > 40);
  }, { passive: true });

  /* ---------- luz que segue o cursor ---------- */
  const luz = $("#cursorLuz");
  addEventListener("pointermove", (e) => { luz.style.left = e.clientX + "px"; luz.style.top = e.clientY + "px"; });

  /* ---------- contadores ---------- */
  function contar(el) {
    const ate = +el.dataset.ate, pre = el.dataset.pre || "", suf = el.dataset.suf || "", t0 = performance.now(), dur = 1600;
    const passo = (t) => {
      const p = Math.min(1, (t - t0) / dur), v = Math.round(ate * (1 - Math.pow(1 - p, 4)));
      el.textContent = pre + v.toLocaleString("pt-BR") + suf;
      if (p < 1) requestAnimationFrame(passo);
    };
    requestAnimationFrame(passo);
  }

  /* ---------- revelar ao rolar ---------- */
  const obs = new IntersectionObserver((ents) => ents.forEach((e) => {
    if (!e.isIntersecting) return;
    e.target.classList.add("visivel");
    $$(".cont", e.target).forEach((c) => { if (!c.dataset.feito) { c.dataset.feito = 1; contar(c); } });
    if (e.target.classList.contains("cont") && !e.target.dataset.feito) { e.target.dataset.feito = 1; contar(e.target); }
    obs.unobserve(e.target);
  }), { threshold: 0.18 });
  $$(".revelar, .card, .degrau, .chip .cont").forEach((el) => obs.observe(el));

  /* ---------- texto rotativo do título ---------- */
  const frases = ["se faz sozinho", "aprende com você", "confere cada boleto", "não perde nada"];
  const rot = $("#rotativo");
  if (!calmo) {
    let i = 0, j = frases[0].length, apagando = true;
    setTimeout(function digitar() {
      const f = frases[i];
      rot.textContent = f.slice(0, j);
      if (apagando) { j--; if (j < 0) { apagando = false; i = (i + 1) % frases.length; j = 0; } }
      else { j++; if (j > frases[i].length) { apagando = true; return setTimeout(digitar, 2200); } }
      setTimeout(digitar, apagando ? 35 : 70);
    }, 2600);
  }

  /* ---------- rede de partículas no hero ---------- */
  const cv = $("#rede"), ctx = cv.getContext("2d");
  let pts = [], W, H, mouse = { x: -999, y: -999 };
  function medir() {
    const r = devicePixelRatio || 1;
    W = cv.clientWidth; H = cv.clientHeight; cv.width = W * r; cv.height = H * r; ctx.setTransform(r, 0, 0, r, 0, 0);
    const n = Math.min(110, Math.floor(W * H / 14000));
    pts = Array.from({ length: n }, () => ({ x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - .5) * .35, vy: (Math.random() - .5) * .35 }));
  }
  cv.parentElement.addEventListener("pointermove", (e) => { const b = cv.getBoundingClientRect(); mouse = { x: e.clientX - b.left, y: e.clientY - b.top }; });
  cv.parentElement.addEventListener("pointerleave", () => { mouse = { x: -999, y: -999 }; });
  function desenhar() {
    ctx.clearRect(0, 0, W, H);
    for (const p of pts) {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > W) p.vx *= -1; if (p.y < 0 || p.y > H) p.vy *= -1;
      const dm = Math.hypot(p.x - mouse.x, p.y - mouse.y);
      if (dm < 140) { p.x += (p.x - mouse.x) / dm * .8; p.y += (p.y - mouse.y) / dm * .8; }
    }
    for (let a = 0; a < pts.length; a++) for (let b = a + 1; b < pts.length; b++) {
      const d = Math.hypot(pts[a].x - pts[b].x, pts[a].y - pts[b].y);
      if (d < 130) { ctx.strokeStyle = `rgba(201,205,210,${(1 - d / 130) * .16})`; ctx.beginPath(); ctx.moveTo(pts[a].x, pts[a].y); ctx.lineTo(pts[b].x, pts[b].y); ctx.stroke(); }
    }
    for (const p of pts) { ctx.fillStyle = "rgba(220,224,229,.55)"; ctx.beginPath(); ctx.arc(p.x, p.y, 1.4, 0, 7); ctx.fill(); }
    if (!calmo) requestAnimationFrame(desenhar);
  }
  medir(); desenhar(); addEventListener("resize", medir);

  /* ---------- moldura 3D do hero ---------- */
  const mold = $("#moldura"), hv = $("#heroVisual");
  hv.addEventListener("pointermove", (e) => {
    const b = hv.getBoundingClientRect(), x = (e.clientX - b.left) / b.width - .5, y = (e.clientY - b.top) / b.height - .5;
    mold.style.transform = `rotateY(${-14 + x * 16}deg) rotateX(${6 - y * 12}deg)`;
  });
  hv.addEventListener("pointerleave", () => { mold.style.transform = ""; });

  /* ---------- cards com inclinação e brilho ---------- */
  $$("[data-tilt]").forEach((el) => {
    el.addEventListener("pointermove", (e) => {
      const b = el.getBoundingClientRect(), x = (e.clientX - b.left) / b.width, y = (e.clientY - b.top) / b.height;
      el.style.setProperty("--mx", x * 100 + "%"); el.style.setProperty("--my", y * 100 + "%");
      el.style.transform = `perspective(900px) rotateY(${(x - .5) * 10}deg) rotateX(${(.5 - y) * 10}deg) translateY(-4px)`;
    });
    el.addEventListener("pointerleave", () => { el.style.transform = ""; });
  });

  /* ---------- como funciona: palco fixo ---------- */
  const cenas = $$(".cena"), passos = $$(".passo");
  const linhas = [
    ["PAGTO BOLETO 00104 FRIGORIFICO", "−5.131,40", "Fornecedor de açougue", "ok"],
    ["ENERGIA ELETRICA CONCESSIONARIA", "−7.188,22", "Energia elétrica", "ok"],
    ["PIX ENVIADO MARIA DA SILVA", "−350,00", "Revisar: Freelance?", "al"],
    ["RECEBIMENTO CARTOES ADQUIRENTE", "+14.902,10", "Receita de vendas", "ok"],
    ["TARIFA PACOTE DE SERVICOS", "−189,00", "Despesas bancárias", "ok"],
    ["PAGTO BOLETO 00106 HORTIFRUTI", "−1.702,90", "Fornecedor de hortifruti", "ok"],
  ];
  const ld = $("#linhasDemo");
  ld.innerHTML = linhas.map(([d, v]) => `<div class="ld"><span>${d}</span><span class="v">${v}</span><span class="c">classificando…</span></div>`).join("");
  const graf = $("#graficoDemo");
  const meses = [["Mai", 62], ["Jun", 58], ["Jul", 66], ["Ago", 61], ["Set", 70], ["Out", 74], ["Nov", 79, 1], ["Dez", 92, 1]];
  graf.innerHTML = meses.map(([m, , p]) => `<div class="b ${p ? "proj" : ""}"><small>${m}</small></div>`).join("");
  let atual = -1, timers = [];
  function cena(i) {
    if (i === atual) return; atual = i;
    timers.forEach(clearTimeout); timers = [];
    cenas.forEach((c, k) => c.classList.toggle("ativa", k === i));
    passos.forEach((p, k) => p.classList.toggle("ativo", k === i));
    const rows = $$(".ld", ld);
    rows.forEach((r) => { r.classList.remove("on"); const c = $(".c", r); c.className = "c"; c.textContent = "classificando…"; });
    if (i === 1) rows.forEach((r, k) => {
      timers.push(setTimeout(() => r.classList.add("on"), k * 180));
      timers.push(setTimeout(() => { const c = $(".c", r); c.classList.add(linhas[k][3]); c.textContent = linhas[k][2]; }, 900 + k * 260));
    });
    $$(".b", graf).forEach((b, k) => { b.style.height = i === 3 ? meses[k][1] + "%" : "0"; b.style.transitionDelay = k * 90 + "ms"; });
  }
  const obsPasso = new IntersectionObserver((ents) => ents.forEach((e) => { if (e.isIntersecting) cena(+e.target.dataset.passo); }),
    { rootMargin: "-45% 0px -45% 0px" });
  passos.forEach((p) => obsPasso.observe(p));
  cena(0);

  /* ---------- escada de conciliação ---------- */
  const degraus = $$(".degrau");
  const obsEsc = new IntersectionObserver((ents) => ents.forEach((e) => {
    if (!e.isIntersecting) return;
    degraus.forEach((d, k) => setTimeout(() => {
      d.classList.add("visivel"); $(".forca i", d).style.width = d.dataset.forca + "%";
    }, k * 120));
    obsEsc.disconnect();
  }), { threshold: .2 });
  obsEsc.observe($("#escada"));
  let acesa = 0;
  setInterval(() => { if (calmo) return; degraus.forEach((d, k) => d.classList.toggle("acesa", k === acesa)); acesa = (acesa + 1) % degraus.length; }, 1300);

  /* ---------- comparador antes/depois ---------- */
  const comp = $("#comparador");
  let arrastando = false;
  const mover = (x) => { const b = comp.getBoundingClientRect(); comp.style.setProperty("--corte", Math.max(4, Math.min(96, (x - b.left) / b.width * 100)) + "%"); };
  comp.addEventListener("pointerdown", (e) => { arrastando = true; comp.setPointerCapture(e.pointerId); mover(e.clientX); });
  comp.addEventListener("pointermove", (e) => arrastando && mover(e.clientX));
  comp.addEventListener("pointerup", () => { arrastando = false; });
  const obsComp = new IntersectionObserver((ents) => {
    if (!ents[0].isIntersecting || calmo) return; obsComp.disconnect();
    let t = 0; const anim = () => { t += .02; comp.style.setProperty("--corte", 50 + Math.sin(t * 2) * 30 * (1 - t / 3) + "%"); if (t < 3 && !arrastando) requestAnimationFrame(anim); };
    anim();
  }, { threshold: .5 });
  obsComp.observe(comp);
})();
