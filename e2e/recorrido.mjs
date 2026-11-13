// Recorrido de punta a punta con un navegador real (Playwright, en contenedor).
// Uso: make e2e   (levanta contra el stack de desarrollo y guarda capturas en e2e/out)
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { deflateSync } from "node:zlib";

const BASE = process.env.BASE_URL ?? "http://frontend:3000";
const EMAIL = process.env.ADMIN_EMAIL;
const CLAVE = process.env.ADMIN_PASSWORD;
const ARTICULO = `E2E ${Date.now() % 100000}`;
mkdirSync("out", { recursive: true });

// PNG de 96x96 generado aquí (sin dependencias), para probar la subida de foto.
function crearPng(w, h) {
  const crcTabla = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc = (buf) => {
    let c = 0xffffffff;
    for (const x of buf) c = crcTabla[(c ^ x) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  const trozo = (tipo, datos) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(datos.length);
    const cuerpo = Buffer.concat([Buffer.from(tipo), datos]);
    const sum = Buffer.alloc(4);
    sum.writeUInt32BE(crc(cuerpo));
    return Buffer.concat([len, cuerpo, sum]);
  };
  const cab = Buffer.alloc(13);
  cab.writeUInt32BE(w, 0);
  cab.writeUInt32BE(h, 4);
  cab[8] = 8; // bits
  cab[9] = 2; // RGB
  const filas = [];
  for (let y = 0; y < h; y++) {
    const fila = Buffer.alloc(1 + w * 3);
    for (let x = 0; x < w; x++) {
      fila[1 + x * 3] = 176 - Math.floor((y / h) * 60);
      fila[2 + x * 3] = 72 + Math.floor((x / w) * 80);
      fila[3 + x * 3] = 40;
    }
    filas.push(fila);
  }
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    trozo("IHDR", cab),
    trozo("IDAT", deflateSync(Buffer.concat(filas))),
    trozo("IEND", Buffer.alloc(0)),
  ]);
}
writeFileSync("foto.png", crearPng(96, 96));

let fallos = 0;
const ok = (cond, msg) => {
  console.log(`${cond ? "  ok  " : "  FALLA"} ${msg}`);
  if (!cond) fallos++;
};

const navegador = await chromium.launch();
const contexto = await navegador.newContext({ viewport: { width: 1280, height: 900 }, locale: "es-CO", timezoneId: "America/Bogota" });
const pagina = await contexto.newPage();
const consola = [];
pagina.on("console", (m) => ["error", "warning"].includes(m.type()) && consola.push(`[${m.type()}] ${m.text()}`));
pagina.on("pageerror", (e) => consola.push(`[pageerror] ${e.message}`));

const foto = (n) => pagina.screenshot({ path: `out/${n}.png`, fullPage: false });
const sinScrollHorizontal = async (ancho) => {
  await pagina.setViewportSize({ width: ancho, height: 800 });
  await pagina.waitForTimeout(250);
  return pagina.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
};

async function stockDe(nombre) {
  await pagina.goto(`${BASE}/panel/inventario`);
  const fila = pagina.locator("button.fila", { hasText: nombre });
  await fila.waitFor();
  return Number((await fila.locator(".stock-num").innerText()).trim());
}

console.log("Público");
await pagina.goto(BASE);
await pagina.getByRole("heading", { level: 1 }).waitFor();
await foto("01-publico-desktop");
ok((await pagina.locator("li.articulo").count()) >= 1, "el catálogo muestra artículos");
ok(!(await pagina.content()).includes("stock_minimo"), "el HTML público no expone campos internos");
for (const w of [320, 375, 414, 768]) ok(await sinScrollHorizontal(w), `catálogo sin scroll horizontal a ${w}px`);
await pagina.setViewportSize({ width: 375, height: 800 });
await foto("02-publico-movil");
await pagina.setViewportSize({ width: 1280, height: 900 });

console.log("Panel: entrar");
await pagina.goto(`${BASE}/panel`);
await pagina.waitForURL("**/entrar");
ok(true, "/panel sin sesión redirige a /entrar");
// Un correo inexistente: así la prueba no bloquea la cuenta real (el límite es de 5 fallos por correo).
await pagina.getByLabel("Correo").fill("nadie@example.com");
await pagina.getByLabel("Contraseña").fill("clave-equivocada-123");
await pagina.getByRole("button", { name: "Entrar" }).click();
await pagina.locator(".alerta").waitFor();
ok((await pagina.locator(".alerta").innerText()).includes("incorrectos"), "clave incorrecta muestra un mensaje claro");
await foto("03-entrar-error");
await pagina.getByLabel("Correo").fill(EMAIL);
await pagina.getByLabel("Contraseña").fill(CLAVE);
await pagina.getByRole("button", { name: "Entrar" }).click();
await pagina.waitForURL("**/panel");
await pagina.getByRole("heading", { name: "Hoy" }).waitFor();
await foto("04-inicio");

console.log("Artículos");
await pagina.goto(`${BASE}/panel/articulos`);
await pagina.getByRole("button", { name: /Nuevo artículo/ }).first().click();
await pagina.getByLabel("Nombre").fill(ARTICULO);
await pagina.getByLabel("Descripción").fill("Artículo creado por la prueba de punta a punta.");
await pagina.getByLabel("Precio de venta (COP)").fill("10000");
await pagina.getByLabel("Avisar si quedan").fill("3");
await pagina.locator('input[type="file"]').setInputFiles("foto.png");
await foto("05-articulo-hoja");
await pagina.getByRole("button", { name: "Guardar" }).click();
await pagina.locator("button.fila", { hasText: ARTICULO }).waitFor({ timeout: 8000 }).catch(async () => {
  console.log("  (no apareció la fila) alerta:", await pagina.locator(".alerta").allInnerTexts());
  await foto("99-articulo-fallo");
  throw new Error("no se creó el artículo");
});
ok(true, "artículo creado y listado");
await foto("06-articulos");
ok(!!(await pagina.locator("button.fila", { hasText: ARTICULO }).locator("img").count()), "la foto subida se ve en la lista");

console.log("Producción → inventario");
await pagina.goto(`${BASE}/panel/produccion`);
const ficha = pagina.locator("button.ficha", { hasText: ARTICULO });
await ficha.click();
await ficha.click();
await ficha.click();
await pagina.getByRole("button", { name: "Sumar al inventario" }).click();
await pagina.getByText(/entraron al inventario/).waitFor();
await foto("07-produccion");
ok((await stockDe(ARTICULO)) === 3, "producir 3 deja 3 en inventario");

console.log("Pedido público (no debe tocar el inventario)");
const contextoPublico = await navegador.newContext({ viewport: { width: 375, height: 800 }, locale: "es-CO" });
const publica = await contextoPublico.newPage();
await publica.goto(BASE);
const tarjeta = publica.locator("li.articulo", { hasText: ARTICULO });
await tarjeta.waitFor();
await tarjeta.getByRole("button", { name: /Pedir/ }).click();
await publica.getByLabel("Tu nombre").fill("Cliente de Prueba");
await publica.getByLabel("Tu WhatsApp").fill("300 123 4567");
await publica.getByRole("button", { name: /Agregar una unidad/ }).click();
await publica.screenshot({ path: "out/08-pedido-movil.png" });
await publica.getByRole("button", { name: "Enviar pedido" }).click();
await publica.getByText("Pedido enviado").waitFor();
await publica.screenshot({ path: "out/09-pedido-enviado.png" });
ok(true, "pedido enviado desde el catálogo");
ok((await stockDe(ARTICULO)) === 3, "el pedido NO cambió el inventario");

console.log("Pedidos en el panel");
await pagina.goto(`${BASE}/panel/pedidos`);
await pagina.getByText("Cliente de Prueba").first().waitFor();
await foto("10-pedidos");
ok(await pagina.getByRole("link", { name: /Escribir por WhatsApp/ }).first().getAttribute("href").then((h) => h?.startsWith("https://wa.me/573001234567")), "el enlace de WhatsApp lleva el indicativo 57");

console.log("Venta + Deshacer");
await pagina.goto(`${BASE}/panel/vender`);
const fv = pagina.locator("button.ficha", { hasText: ARTICULO });
await fv.click();
await fv.click();
await foto("11-vender");
ok((await pagina.locator(".ticket__total strong").innerText()).replace(/\D/g, "") === "20000", "el total en vivo suma 2 × $10.000");
await pagina.getByRole("button", { name: "Registrar venta" }).click();
await pagina.getByText(/Venta registrada/).waitFor();
await foto("12-venta-registrada");
ok((await stockDe(ARTICULO)) === 1, "vender 2 deja 1 en inventario");
await pagina.goto(`${BASE}/panel/vender`);
await pagina.getByText(/Ventas de hoy/).waitFor();
await pagina.getByRole("button", { name: "Anular" }).first().click();
await pagina.getByRole("button", { name: "Sí, anular" }).click();
await pagina.getByText(/Venta anulada/).waitFor();
ok((await stockDe(ARTICULO)) === 3, "anular devuelve las piezas al inventario");

console.log("Venta sin stock suficiente");
await pagina.goto(`${BASE}/panel/vender`);
const f2 = pagina.locator("button.ficha", { hasText: ARTICULO });
for (let i = 0; i < 4; i++) await f2.click();
await pagina.getByText(/solo quedan 3/).waitFor();
ok(true, "no deja vender más de lo que hay y lo explica");

console.log("Responsive del panel");
for (const ruta of ["", "/vender", "/produccion", "/inventario", "/articulos", "/pedidos"]) {
  await pagina.goto(`${BASE}/panel${ruta}`);
  await pagina.getByRole("heading", { level: 1 }).waitFor();
  for (const w of [320, 375, 414, 768]) {
    const bien = await sinScrollHorizontal(w);
    ok(bien, `/panel${ruta} sin scroll horizontal a ${w}px`);
  }
  await pagina.setViewportSize({ width: 375, height: 800 });
  await pagina.screenshot({ path: `out/m${ruta.replace("/", "-") || "-inicio"}.png` });
  await pagina.setViewportSize({ width: 1280, height: 900 });
}

console.log("Salir");
await pagina.goto(`${BASE}/panel`);
await pagina.getByRole("button", { name: "Salir" }).first().click();
await pagina.waitForURL("**/entrar");
await pagina.goto(`${BASE}/panel`);
await pagina.waitForURL("**/entrar");
ok(true, "tras salir, /panel vuelve a pedir sesión");

const csp = consola.filter((m) => /content security policy|refused to|violat/i.test(m));
ok(csp.length === 0, `sin violaciones de CSP en consola ${csp.length ? "\n" + csp.join("\n") : ""}`);
const otros = consola.filter((m) => !csp.includes(m));
if (otros.length) console.log("Consola:\n" + otros.join("\n"));

await navegador.close();
console.log(fallos ? `\n${fallos} comprobaciones fallaron` : "\nTodo bien");
process.exit(fallos ? 1 : 0);
