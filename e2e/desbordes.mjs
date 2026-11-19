// Detector de texto que se sale de su caja. Recorre el sitio público y el panel a varios anchos y,
// para cada texto, comprueba que cabe dentro de la tarjeta (o caja con fondo/borde) que lo contiene y
// que ningún elemento desborda por dentro (scrollWidth > clientWidth). Uso: make desbordes
import { chromium } from "playwright";

const BASE = process.env.BASE || "http://frontend:3000";
const ANCHOS = (process.env.ANCHOS || "1800,1440,1280,1024,768,414,390,360,320").split(",").map(Number);
const hallazgos = new Map();

const revisar = () => {
  const out = [];
  const visible = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none"; };
  const camino = (e) => { const p = []; for (let n = e; n && n !== document.body && p.length < 4; n = n.parentElement) p.unshift(n.tagName.toLowerCase() + (n.className && typeof n.className === "string" ? "." + n.className.trim().split(/\s+/)[0] : "")); return p.join(" > "); };
  const caja = (e) => { for (let n = e.parentElement; n && n !== document.body && n !== document.documentElement; n = n.parentElement) { const s = getComputedStyle(n); const fondo = s.backgroundColor; const conFondo = fondo && !/rgba?\(\s*0,\s*0,\s*0,\s*0\)|transparent/.test(fondo); const borde = parseFloat(s.borderTopWidth) > 0 && s.borderTopStyle !== "none"; if ((conFondo || borde) && s.display !== "contents" && !n.matches("dialog")) return n; if (n.matches("dialog")) return n; } return null; };
  const rec = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let t = rec.nextNode(); t; t = rec.nextNode()) {
    const texto = t.textContent.trim();
    if (!texto) continue;
    const el = t.parentElement;
    if (!el || !visible(el) || el.closest(".visually-hidden, [aria-hidden='true'].trampa, .trampa, script, style, noscript")) continue;
    const r = document.createRange(); r.selectNodeContents(t);
    for (const f of r.getClientRects()) {
      if (f.width < 1) continue;
      const c = caja(el);
      if (!c) continue;
      const cr = c.getBoundingClientRect();
      // Un contenedor con scroll propio (lista, hoja) no cuenta: su contenido se desplaza a propósito.
      let ancestroScroll = false;
      for (let n = el; n && n !== c.parentElement; n = n.parentElement) { const ox = getComputedStyle(n).overflowX; if (ox === "auto" || ox === "scroll") ancestroScroll = true; if (n === c) break; }
      if (ancestroScroll) continue;
      if (f.right > cr.right + 1.5 || f.left < cr.left - 1.5) { out.push({ tipo: "texto fuera de su caja", donde: camino(el), caja: camino(c), texto: texto.slice(0, 48), sobra: Math.round(Math.max(f.right - cr.right, cr.left - f.left)) }); break; }
    }
  }
  for (const e of document.querySelectorAll("body *")) {
    if (!visible(e) || e.closest(".visually-hidden, .trampa") || e.matches("svg, svg *, img, input, textarea, select")) continue;
    const s = getComputedStyle(e);
    if (s.overflowX === "auto" || s.overflowX === "scroll" || s.overflowX === "hidden") {
      if (s.overflowX === "hidden" && e.scrollWidth > e.clientWidth + 1 && e.textContent.trim() && !e.matches(".foto, .encuadre, .progreso, .barras, .lista, .articulo, .ticket")) out.push({ tipo: "texto recortado (overflow oculto)", donde: camino(e), texto: e.textContent.trim().slice(0, 48), sobra: e.scrollWidth - e.clientWidth });
      continue;
    }
    if (e.scrollWidth > e.clientWidth + 1 && e.clientWidth > 0 && e.textContent.trim() && !e.matches("html, body")) out.push({ tipo: "contenido desborda su elemento", donde: camino(e), texto: e.textContent.trim().slice(0, 48), sobra: e.scrollWidth - e.clientWidth });
  }
  // Palabras partidas a mitad («efectiv/o»): una palabra cuyo rectángulo ocupa dos o más líneas.
  const lineas = (r) => new Set([...r.getClientRects()].filter((f) => f.width > 0.5).map((f) => Math.round(f.top / 4))).size;
  const rec2 = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let t = rec2.nextNode(); t; t = rec2.nextNode()) {
    const el = t.parentElement;
    if (!el || !visible(el) || el.closest(".visually-hidden, .trampa, script, style, noscript, [hidden]")) continue;
    for (const m of t.textContent.matchAll(/\S{4,}/g)) {
      if (/[-\/—–·_.,:;+()]/.test(m[0])) continue; // ahí el navegador puede cortar a propósito (nombres de archivo, guiones)
      const r = document.createRange(); r.setStart(t, m.index); r.setEnd(t, m.index + m[0].length);
      if (lineas(r) > 1) { out.push({ tipo: "palabra partida a mitad", donde: camino(el), texto: m[0], sobra: 0 }); break; }
    }
  }
  // Celdas, números, etiquetas y botones con texto corto: nunca deben partirse en varias líneas.
  for (const e of document.querySelectorAll("td, th, .num, strong, .etiqueta, .chip, .btn")) {
    if (!visible(e) || e.closest(".visually-hidden, .trampa") || e.children.length > 0) continue;
    const texto = e.textContent.trim();
    if (!texto || texto.length > 24 || texto.split(/\s+/).length > 3 || e.matches("th.t-nombre, [class*='nombre']")) continue; // los nombres y frases largas pueden bajar de línea
    const r = document.createRange(); r.selectNodeContents(e);
    if (lineas(r) > 1) out.push({ tipo: "texto corto partido en varias líneas", donde: camino(e), texto, sobra: 0 });
  }
  return out;
};

const anotar = (pagina, ancho, lista) => { for (const h of lista) { const k = `${h.tipo}|${h.donde}|${h.caja ?? ""}`; if (!hallazgos.has(k)) hallazgos.set(k, { ...h, paginas: new Set(), anchos: new Set() }); const v = hallazgos.get(k); v.paginas.add(pagina); v.anchos.add(ancho); } };

const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1800, height: 1000 }, locale: "es-CO" });
const p = await ctx.newPage();
const medir = async (nombre, ancho) => { await p.waitForTimeout(700); anotar(nombre, ancho, await p.evaluate(revisar)); };

// --- Público
for (const w of ANCHOS) {
  await p.setViewportSize({ width: w, height: 900 });
  await p.goto(BASE); await p.evaluate(() => localStorage.clear()); await p.reload(); await p.locator("li.articulo").first().waitFor(); await medir("público /", w);
  await p.locator("button.articulo__boton").first().click(); await p.locator("dialog[open]").waitFor(); await medir("público ficha", w);
  const radio = p.getByRole("radio").first(); if (await radio.count()) { await radio.click(); await medir("público ficha (color elegido)", w); }
  const agregar = p.locator("dialog[open]").getByRole("button", { name: "Agregar al pedido" });
  if (await agregar.isEnabled()) {
    await agregar.click(); await p.waitForTimeout(400);
    await p.locator("button.articulo__boton").nth(1).click(); await p.locator("dialog[open]").waitFor();
    const r2 = p.getByRole("radio").first(); if (await r2.count()) await r2.click();
    const ag2 = p.locator("dialog[open]").getByRole("button", { name: "Agregar al pedido" }); if (await ag2.isEnabled()) await ag2.click();
    await p.waitForTimeout(400); await medir("público con carrito (barra)", w);
    await p.locator(".carrito-barra").getByRole("button", { name: "Ver mi pedido" }).click(); await p.locator("dialog[open] .carrito__linea").first().waitFor(); await medir("público mi pedido (carrito)", w);
  }
  await p.keyboard.press("Escape");
}

// --- Panel
await p.setViewportSize({ width: 1800, height: 1000 });
await p.goto(`${BASE}/entrar`);
await p.getByLabel("Correo").fill(process.env.ADMIN_EMAIL);
await p.getByLabel("Contraseña").fill(process.env.ADMIN_PASSWORD);
await p.getByRole("button", { name: "Entrar" }).click();
await p.waitForURL("**/panel", { timeout: 90000 });
// Datos de prueba con nombres LARGOS (lo que escribe una persona real)
await p.evaluate(async () => {
  const h = { "Content-Type": "application/json", "X-Requested-With": "fetch" };
  const lista = await (await fetch("/api/articulos?incluir_inactivos=true", { headers: h })).json();
  if (lista.some((a) => a.nombre.startsWith("Prendedor navideño"))) return;
  const r = await fetch("/api/articulos", { method: "POST", headers: h, body: JSON.stringify({ nombre: "Prendedor navideño de muñeco de jengibre con bufanda y botones dorados — edición especial", descripcion: "Una descripción larga ".repeat(20), precio_venta: 12500, stock_minimo: 2, colores: [{ nombre: "Verde esmeralda oscuro metal", hex: "#0a6b4a" }, { nombre: "Rojo", hex: "#dc2626" }] }) });
  if (!r.ok) throw new Error("No se pudo crear el artículo de prueba: " + r.status + " " + (await r.text()).slice(0, 200));
});
const paginas = ["", "/vender", "/produccion", "/inventario", "/articulos", "/pedidos", "/administracion", "/administracion/impresora"];
for (const w of ANCHOS) {
  await p.setViewportSize({ width: w, height: 1000 });
  for (const r of paginas) {
    await p.goto(`${BASE}/panel${r}`); await p.getByRole("heading", { level: 1 }).waitFor(); await medir(`panel ${r || "/"}`, w);
  }
  await p.goto(`${BASE}/panel/articulos`); await p.getByRole("button", { name: /Nuevo artículo/ }).first().click(); await medir("panel nuevo artículo (hoja)", w); await p.keyboard.press("Escape");
  await p.locator("button.fila", { hasText: "Prendedor navideño" }).first().click(); await medir("panel editar artículo largo (hoja)", w); await p.keyboard.press("Escape");
  await p.goto(`${BASE}/panel/produccion`); await p.getByRole("button", { name: "Parámetros de energía" }).first().click(); await medir("panel parámetros (hoja)", w); await p.keyboard.press("Escape");
  const masLargo = p.locator(".selector").getByRole("button", { name: /Agregar una unidad de Prendedor navideño.*Verde esmeralda/ }); if (await masLargo.count()) { await masLargo.first().click(); await masLargo.first().click(); await medir("panel producción con artículo largo (color)", w); }
  await p.goto(`${BASE}/panel/vender`); await p.getByRole("heading", { level: 1 }).waitFor(); await medir("panel vender con colores", w);
  await p.goto(`${BASE}/panel/inventario`); await p.locator("tr.t-cab", { hasText: "Prendedor navideño" }).first().click(); await p.locator("dialog[open]").waitFor(); await medir("panel inventario ajuste con colores (hoja)", w); await p.keyboard.press("Escape");
}
await b.close();

const lista = [...hallazgos.values()];
if (!lista.length) { console.log("Sin desbordes de texto ✔"); process.exit(0); }
for (const h of lista) console.log(`✘ ${h.tipo}: ${h.donde}${h.caja ? "  (caja: " + h.caja + ")" : ""}\n    «${h.texto}» sobra ${h.sobra}px — en: ${[...h.paginas].slice(0, 4).join(", ")} | anchos: ${[...h.anchos].sort((a, b) => b - a).join(", ")}`);
console.log(`\n${lista.length} tipos de desborde`);
process.exit(1);
