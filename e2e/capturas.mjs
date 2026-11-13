// Capturas de las pantallas principales (sin crear datos): escritorio y móvil. Uso: ver Makefile (`make capturas`).
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
const BASE = process.env.BASE_URL ?? "http://frontend:3000";
mkdirSync("out", { recursive: true });
const nav = await chromium.launch();
const ctx = await nav.newContext({ viewport: { width: 1280, height: 860 }, locale: "es-CO" });
const p = await ctx.newPage();
const foto = async (n, ancho = 1280, alto = 860, full = false) => { await p.setViewportSize({ width: ancho, height: alto }); await p.waitForTimeout(350); await p.screenshot({ path: `out/${n}.png`, fullPage: full }); };
await p.goto(BASE); await p.getByRole("heading", { level: 1 }).waitFor();
await foto("s01-publico"); await foto("s02-publico-movil", 375, 800);
await p.goto(`${BASE}/entrar`); await foto("s03-entrar");
await p.getByLabel("Correo").fill(process.env.ADMIN_EMAIL); await p.getByLabel("Contraseña").fill(process.env.ADMIN_PASSWORD);
await p.getByRole("button", { name: "Entrar" }).click(); await p.waitForURL("**/panel"); await p.getByRole("heading", { name: "Hoy" }).waitFor();
await foto("s04-inicio");
for (const r of ["vender", "produccion", "inventario", "articulos", "pedidos"]) { await p.goto(`${BASE}/panel/${r}`); await p.getByRole("heading", { level: 1 }).waitFor(); await foto(`s05-${r}`); }
await p.goto(`${BASE}/panel`); await p.getByRole("heading", { name: "Hoy" }).waitFor(); await foto("s06-inicio-movil", 375, 800);
await p.goto(`${BASE}/panel/vender`); await p.getByRole("heading", { level: 1 }).waitFor(); await foto("s07-vender-movil", 375, 800);
await p.goto(`${BASE}/panel/articulos`); await p.getByRole("button", { name: /Nuevo artículo/ }).first().click(); await foto("s08-articulo-hoja");
await nav.close(); console.log("capturas listas");
