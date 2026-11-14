// Prueba en WebKit (el motor de Safari/iPhone) con perfiles de dispositivo reales: sin desbordes, hojas, login y panel.
import { webkit, devices } from "playwright";
import { mkdirSync } from "node:fs";
const BASE = process.env.BASE_URL ?? "http://frontend:3000";
mkdirSync("out", { recursive: true });
let fallos = 0;
const ok = (c, m) => { console.log(`${c ? "  ok  " : "  FALLA"} ${m}`); if (!c) fallos++; };
const navegador = await webkit.launch();
for (const nombre of ["iPhone SE", "iPhone 13", "iPhone 15 Pro Max"]) {
  console.log(nombre);
  const ctx = await navegador.newContext({ ...devices[nombre], locale: "es-CO" });
  const p = await ctx.newPage();
  // WebKit reporta como «access control checks / Load failed» las peticiones que se cancelan al cambiar de pantalla: no son errores de la app.
  const errores = []; p.on("pageerror", (e) => !/access control checks|Load failed|cancelled/i.test(e.message) && errores.push(e.message));
  const sinDesborde = () => p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  const tag = nombre.replace(/\s+/g, "");
  await p.goto(BASE); await p.getByRole("heading", { level: 1 }).waitFor();
  ok(await sinDesborde(), "catálogo sin scroll horizontal");
  await p.screenshot({ path: `out/i-${tag}-catalogo.png` });
  await p.locator("button.articulo__boton").first().click();
  ok(await p.locator("dialog[open]").count() === 1, "tocar un artículo abre su ficha (dialog)");
  ok(await sinDesborde(), "ficha del artículo sin desborde");
  await p.locator("dialog[open]").evaluate((d) => Promise.all(d.getAnimations().map((a) => a.finished)));
  await p.screenshot({ path: `out/i-${tag}-ficha.png` });
  if (await p.getByRole("radio").count()) await p.getByRole("radio").first().tap();
  await p.locator("dialog[open]").getByRole("button", { name: /^Pedir/ }).tap();
  await p.getByLabel("Tu nombre").waitFor();
  ok(await sinDesborde(), "hoja de pedido sin desborde");
  const botones = await p.locator("dialog[open] button:visible").evaluateAll((bs) => bs.map((b) => b.getBoundingClientRect().height));
  ok(botones.every((h) => h >= 40), `botones de la hoja con área táctil ≥ 40 px (${Math.min(...botones)|0} px mínimo)`);
  // La hoja entra con una animación de 220 ms; el WebKit del contenedor dibuja pocos cuadros por segundo: se espera a que termine.
  await p.locator("dialog[open]").evaluate((d) => Promise.all(d.getAnimations().map((a) => a.finished)));
  ok(await p.locator("dialog[open]").evaluate((d) => { const r = d.getBoundingClientRect(); return r.height > 200 && r.bottom <= innerHeight + 1 && r.width <= innerWidth + 1; }), "la hoja de pedido queda visible y dentro de la pantalla");
  await p.screenshot({ path: `out/i-${tag}-pedido.png` });
  await p.keyboard.press("Escape");
  await p.goto(`${BASE}/entrar`);
  // Esperar a que React termine de cargar: escribir antes de hidratar lo borra (le pasa a cualquier prueba rápida).
  await p.waitForFunction(() => Object.keys(document.querySelector("form") ?? {}).some((k) => k.startsWith("__react")));
  await p.getByLabel("Correo").fill(process.env.ADMIN_EMAIL); await p.getByLabel("Contraseña").fill(process.env.ADMIN_PASSWORD);
  const tam = await p.getByLabel("Correo").evaluate((e) => parseFloat(getComputedStyle(e).fontSize));
  ok(tam >= 16, `campos con letra ≥ 16 px (${tam}px): Safari no hace zoom al enfocarlos`);
  // Toque real por coordenadas: la comprobación de «estabilidad» de Playwright se cuelga con el iframe de
// Turnstile en WebKit (un toque real sí funciona); así la prueba se parece más a un dedo.
// «Entrar» queda deshabilitado hasta que Turnstile aprueba: se espera a que se habilite como lo haría una persona.
await p.waitForFunction(() => { const b = document.querySelector("form button[type=submit]"); return b && !b.disabled; }, null, { timeout: 25000 });
ok(true, "Turnstile aprobó y habilitó «Entrar»");
await p.getByRole("button", { name: "Entrar" }).scrollIntoViewIfNeeded();
await p.waitForTimeout(400);
const caja = await p.getByRole("button", { name: "Entrar" }).boundingBox();
await p.touchscreen.tap(caja.x + caja.width / 2, caja.y + caja.height / 2);
await p.waitForURL("**/panel", { timeout: 20000 });
ok(true, "el toque en «Entrar» inicia sesión");
  for (const r of ["", "/vender", "/produccion", "/inventario", "/articulos", "/pedidos", "/administracion", "/administracion/impresora"]) {
    await p.goto(`${BASE}/panel${r}`); await p.getByRole("heading", { level: 1 }).waitFor();
    ok(await sinDesborde(), `/panel${r} sin scroll horizontal`);
  }
  const pestanas = await p.goto(`${BASE}/panel/vender`).then(() => p.locator("nav.pestanas").boundingBox());
  const vp = p.viewportSize();
  ok(!!pestanas && Math.round(pestanas.y + pestanas.height) <= vp.height + 1, "la barra inferior queda dentro de la pantalla");
  await p.screenshot({ path: `out/i-${tag}-vender.png` });
  ok(errores.length === 0, `sin errores de JavaScript${errores.length ? ": " + errores[0] : ""}`);
  await ctx.close();
}
await navegador.close();
console.log(fallos ? `\n${fallos} fallaron` : "\nTodo bien en WebKit");
process.exit(fallos ? 1 : 0);
