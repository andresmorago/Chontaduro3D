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
await pagina.getByLabel("Correo").fill(`nadie-${Date.now()}@example.com`); // distinto cada corrida: el límite por correo (5 por 15 min) no se acumula
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

console.log("Administración");
const CORREO_NUEVO = `e2e-${Date.now() % 100000}@ejemplo.co`;
await pagina.goto(`${BASE}/panel/administracion`);
await pagina.getByRole("heading", { name: "Usuarios" }).waitFor();
await pagina.getByRole("button", { name: "Nuevo usuario" }).click();
await pagina.getByLabel("Nombre").fill("Persona de Prueba");
await pagina.getByLabel("Correo").fill(CORREO_NUEVO);
await pagina.getByRole("button", { name: "Generar contraseña" }).click();
ok((await pagina.getByLabel("Contraseña temporal").inputValue()).length === 16, "el generador entrega una contraseña de 16 caracteres");
await foto("13-usuario-nuevo");
await pagina.getByRole("button", { name: "Crear usuario" }).click();
await pagina.locator("button.fila", { hasText: CORREO_NUEVO }).waitFor();
ok(true, "usuario creado y listado");
await foto("14-administracion");
await pagina.locator("button.fila", { hasText: CORREO_NUEVO }).click();
await pagina.getByRole("button", { name: "Generar contraseña" }).click();
await pagina.getByRole("button", { name: "Restablecer contraseña" }).click();
await pagina.getByText(/Contraseña restablecida/).waitFor();
ok(true, "contraseña de otro usuario restablecida");
await pagina.getByRole("button", { name: "Desactivar usuario" }).click();
await pagina.getByRole("button", { name: "Sí, desactivar" }).click();
await pagina.locator("button.fila", { hasText: CORREO_NUEVO }).getByText("Desactivado").waitFor();
ok(true, "usuario desactivado (queda en la lista, sin acceso)");
ok(await pagina.locator("button.fila", { hasText: EMAIL }).getByText("Tú").count() === 1, "mi propio usuario aparece marcado «Tú»");

console.log("Artículos");
await pagina.goto(`${BASE}/panel/articulos`);
await pagina.getByRole("button", { name: /Nuevo artículo/ }).first().click();
await pagina.getByLabel("Nombre").fill(ARTICULO);
await pagina.getByLabel("Descripción").fill("Artículo creado por la prueba de punta a punta.");
await pagina.getByLabel("Precio de venta (COP)").fill("10000");
await pagina.getByLabel("Avisar si quedan").fill("3");
await pagina.getByLabel("Elegir foto", { exact: true }).setInputFiles("foto.png");
// Encuadre: zoom y arrastre sobre la foto principal
await pagina.locator(".encuadre").first().waitFor();
await pagina.getByLabel(`Zoom de ${ARTICULO}`).fill("2");
const caja = await pagina.locator(".encuadre").first().boundingBox();
await pagina.mouse.move(caja.x + caja.width / 2, caja.y + caja.height / 2);
await pagina.mouse.down();
await pagina.mouse.move(caja.x + caja.width / 2 + 40, caja.y + caja.height / 2 + 30, { steps: 6 });
await pagina.mouse.up();
await foto("05a-encuadre");
// Colores: dos, para que el cliente elija
await pagina.getByRole("button", { name: "+ Agregar color" }).click();
await pagina.getByLabel("Nombre del color 1").fill("Rojo");
await pagina.getByRole("button", { name: "+ Agregar color" }).click();
await pagina.getByLabel("Nombre del color 2").fill("Azul");
// Foto propia del color Rojo, en HEIC (el color Azul queda sin foto: es opcional)
await pagina.getByRole("button", { name: "Foto del color Rojo" }).click();
await pagina.getByLabel("Elegir foto del color").setInputFiles("foto.heic");
await pagina.getByText(/Foto HEIC lista/).waitFor();
ok(true, "un archivo HEIC se acepta y avisa que se convierte al guardar");
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
await pagina.locator("button.fila", { hasText: ARTICULO }).click();
await pagina.getByLabel(`Zoom de ${ARTICULO}`).waitFor();
ok(Number(await pagina.getByLabel(`Zoom de ${ARTICULO}`).inputValue()) === 2, "el zoom elegido quedó guardado");
await pagina.getByRole("button", { name: "Foto del color Rojo" }).click();
await pagina.getByLabel("Zoom de el color Rojo").waitFor();
ok(true, "el HEIC del color se convirtió en el servidor y ya se puede encuadrar");
await foto("05b-foto-de-color");
ok((await pagina.getByRole("button", { name: "Foto del color Azul" }).locator("svg").count()) === 1, "el color sin foto no la exige");
await pagina.getByRole("button", { name: "Cancelar" }).click();

console.log("Producción → inventario");
await pagina.goto(`${BASE}/panel/produccion`);
const ficha = pagina.locator("button.ficha", { hasText: ARTICULO });
await ficha.click();
await ficha.click();
await ficha.click();
// Parámetros de energía (universales) + filamento y tiempo del lote
await pagina.getByRole("button", { name: "Parámetros de energía" }).first().click();
await pagina.getByLabel("Precio del kWh (COP)").fill("800");
await pagina.getByLabel("Potencia promedio de la impresora (W)").fill("200");
await pagina.getByRole("button", { name: "Guardar" }).click();
await pagina.getByText(/Parámetros guardados/).waitFor();
await pagina.getByLabel("Gramos de filamento del lote").fill("187.5");
await pagina.getByLabel("Horas").fill("2");
await pagina.getByLabel("Minutos").fill("30");
ok((await pagina.locator(".filtiempo .field__hint").first().innerText()).includes("0,5 kWh") || (await pagina.locator(".filtiempo").innerText()).includes("0,5 kWh"), "vista previa: 200 W × 2 h 30 min = 0,5 kWh");
await foto("07a-produccion-filamento");
await pagina.getByRole("button", { name: "Sumar al inventario" }).click();
await pagina.getByText(/entraron al inventario/).waitFor();
await foto("07-produccion");
// Se espera a que el historial muestre el lote recién guardado (la recarga llega después del aviso).
const filaMeta = pagina.locator(".lista .fila__meta").filter({ hasText: "187,5 g" }).first();
await filaMeta.waitFor();
const meta = (await filaMeta.innerText()).replace(/\u00a0/g, " ");
ok(meta.includes("187,5 g") && meta.includes("2 h 30 min") && meta.includes("0,5 kWh") && meta.includes("$ 400"), `el lote guarda gramos, tiempo y energía (${meta.replace(/\n/g, " ")})`);
ok((await stockDe(ARTICULO)) === 3, "producir 3 deja 3 en inventario");

console.log("Editar un lote ya guardado");
await pagina.goto(`${BASE}/panel/produccion`);
await pagina.getByRole("button", { name: /Editar el lote/ }).first().click();
await pagina.getByRole("heading", { name: "Editar lote" }).waitFor();
await foto("07c-lote-editar");
await pagina.locator("dialog[open]").getByRole("button", { name: new RegExp(`Agregar una unidad de ${ARTICULO}`) }).click();
await pagina.getByRole("button", { name: "Guardar cambios" }).click();
await pagina.getByText(/Lote corregido/).waitFor();
ok((await stockDe(ARTICULO)) === 4, "editar el lote de 3 a 4 sube el inventario a 4 (solo la diferencia)");
await pagina.goto(`${BASE}/panel/produccion`);
await pagina.getByRole("button", { name: /Editar el lote/ }).first().click();
await pagina.locator("dialog[open]").getByRole("button", { name: new RegExp(`Quitar una unidad de ${ARTICULO}`) }).click();
await pagina.getByRole("button", { name: "Guardar cambios" }).click();
await pagina.getByText(/Lote corregido/).waitFor();
await pagina.goto(`${BASE}/panel/produccion`);
const metaEditada = (await pagina.locator(".lista .fila__meta").first().innerText()).replace(/\u00a0/g, " ");
ok(metaEditada.includes("187,5 g") && metaEditada.includes("2 h 30 min"), "el lote editado conserva filamento y tiempo");
ok((await stockDe(ARTICULO)) === 3, "volver el lote a 3 deja el inventario en 3");

console.log("Carga retrospectiva");
const FECHA_VIEJA = new Date(Date.now() - 400 * 864e5).toISOString().slice(0, 10);
await pagina.goto(`${BASE}/panel/produccion`);
await pagina.locator("button.ficha", { hasText: ARTICULO }).click();
await pagina.locator('input[type="date"]').fill(FECHA_VIEJA);
await pagina.getByText(/Carga retrospectiva/).waitFor();
await foto("07b-produccion-retrospectiva");
await pagina.getByLabel("Sumar al inventario actual").uncheck();
await pagina.getByRole("button", { name: "Sumar al inventario" }).click();
await pagina.getByText(/sin sumar al stock/).waitFor();
const viejo = (await pagina.locator(".lista .fila__meta").filter({ hasText: "solo historial" }).first().innerText()).replace(/\u00a0/g, " ");
ok(viejo.includes("solo historial"), `el lote viejo queda en el historial como «solo historial» (${viejo.replace(/\n/g, " ")})`);
ok((await stockDe(ARTICULO)) === 3, "una carga histórica sin sumar NO cambia el inventario de hoy");

console.log("Trabajos de la impresora → producción");
await pagina.goto(`${BASE}/panel/produccion`);
const trabA = pagina.locator(".trabajo", { hasText: "E2E trabajo A" });
await trabA.waitFor();
const metaA = (await trabA.locator(".trabajo__meta").innerText()).replace(/\u00a0/g, " ");
ok(metaA.includes("2 h 5 min (estimado)") && metaA.includes("42,5 g (estimado)"), `el trabajo muestra tiempo y gramos del archivo (${metaA.replace(/\n/g, " ")})`);
await foto("07e-trabajos-impresora");
await trabA.getByRole("button", { name: /Importar el trabajo/ }).click();
await pagina.getByText(/Datos del trabajo/).waitFor();
ok((await pagina.getByLabel("Horas").inputValue()) === "2" && (await pagina.getByLabel("Minutos").inputValue()) === "5", "importar rellena horas y minutos (2 h 5 min)");
ok((await pagina.locator(".filtiempo").innerText()).replace(/\u00a0/g, " ").includes("42,5 g"), "con dos colores rellena el desglose por filamento (total 42,5 g)");
await pagina.locator("button.ficha", { hasText: ARTICULO }).click();
await pagina.getByLabel("Sumar al inventario actual").uncheck();
await foto("07f-trabajo-importado");
await pagina.getByRole("button", { name: "Sumar al inventario" }).click();
await pagina.getByText(/sin sumar al stock/).waitFor();
await pagina.locator(".trabajo", { hasText: "E2E trabajo A" }).waitFor({ state: "detached" });
ok(true, "el trabajo importado sale de la bandeja");
ok((await pagina.locator(".lista .fila__meta").filter({ hasText: "de la impresora" }).count()) >= 1, "el lote queda marcado «de la impresora»");
ok((await stockDe(ARTICULO)) === 3, "importar sin sumar no cambia el inventario");
await pagina.goto(`${BASE}/panel/produccion`);
const trabB = pagina.locator(".trabajo", { hasText: "E2E trabajo B" });
await trabB.getByRole("button", { name: /Ignorar el trabajo/ }).click();
await pagina.getByText(/Trabajo ignorado/).waitFor();
await pagina.getByRole("button", { name: "Ignorados" }).click();
await pagina.locator(".trabajo", { hasText: "E2E trabajo B" }).getByRole("button", { name: /Restaurar/ }).click();
await pagina.getByText(/devuelto a la lista/).waitFor();
await pagina.getByRole("button", { name: "Por revisar" }).click();
await pagina.locator(".trabajo", { hasText: "E2E trabajo B" }).waitFor();
ok(true, "ignorar y restaurar un trabajo funciona");

console.log("Administración → Impresora");
await pagina.goto(`${BASE}/panel/administracion`);
await pagina.getByRole("link", { name: "Impresora" }).click();
await pagina.getByRole("heading", { name: "Controles" }).waitFor();
await pagina.locator(".impresora-estado").waitFor();
await foto("07g-impresora");
const estadoImp = (await pagina.locator(".impresora-estado").innerText()).replace(/\u00a0/g, " ");
ok(/Lista|Imprimiendo|En pausa|Terminada|Preparando|Fallida|Sin conexión/.test(estadoImp), `la página de la impresora muestra su estado (${estadoImp.split("\n")[0]})`);
ok((await pagina.getByRole("button", { name: /luz/ }).count()) === 1, "hay control de luz");
ok((await pagina.getByRole("link", { name: "Cuenta y usuarios" }).count()) === 1, "las pestañas de Administración están");

console.log("Pedido público (no debe tocar el inventario)");
const contextoPublico = await navegador.newContext({ viewport: { width: 375, height: 800 }, locale: "es-CO" });
const publica = await contextoPublico.newPage();
await publica.goto(BASE);
const tarjeta = publica.locator("li.articulo", { hasText: ARTICULO });
await tarjeta.waitFor();
const textoTarjeta = (await tarjeta.innerText()).replace(/\u00a0/g, " ");
ok(textoTarjeta.trim() === ARTICULO && !textoTarjeta.includes("$"), `la tarjeta del catálogo muestra solo el nombre (sin precio ni descripción): «${textoTarjeta.trim()}»`);
await tarjeta.locator("button.articulo__boton").click();
await publica.getByText("Artículo creado por la prueba de punta a punta.").waitFor();
ok(true, "al tocar la tarjeta se amplía la información (descripción)");
await publica.screenshot({ path: "out/07d-ficha-movil.png" });
ok((await publica.getByRole("radio").count()) === 2, "la ficha ofrece los 2 colores definidos");
ok(await publica.locator("dialog[open]").getByRole("button", { name: /^Pedir/ }).isDisabled(), "no se puede pedir sin elegir color");
const imgFicha = publica.locator("dialog[open] .detalle__foto img");
await imgFicha.waitFor();
await publica.waitForTimeout(800);
const srcPrincipal = await imgFicha.getAttribute("src");
ok((await imgFicha.evaluate((e) => parseFloat(e.style.width))) >= 150, "la ficha aplica el zoom elegido (la misma foto y encuadre que la tarjeta)");
await publica.getByRole("radio", { name: "Rojo" }).click();
await publica.waitForTimeout(600);
ok((await publica.locator("dialog[open] .detalle__foto img").getAttribute("src")) !== srcPrincipal, "al elegir un color con foto propia la ficha muestra esa foto");
await publica.screenshot({ path: "out/07e-ficha-color.png" });
await publica.getByRole("radio", { name: "Azul" }).click();
await publica.waitForTimeout(600);
ok((await publica.locator("dialog[open] .detalle__foto img").getAttribute("src")) === srcPrincipal, "un color sin foto vuelve a la foto del artículo");
await publica.locator("dialog[open]").getByRole("button", { name: /^Pedir/ }).click();
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
ok((await pagina.locator(".pedido").first().innerText()).includes("Azul"), "el pedido en el panel muestra el color elegido");
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
for (const ruta of ["", "/vender", "/produccion", "/inventario", "/articulos", "/pedidos", "/administracion", "/administracion/impresora"]) {
  await pagina.goto(`${BASE}/panel${ruta}`);
  await pagina.getByRole("heading", { level: 1 }).waitFor();
  for (const w of [320, 375, 414, 768]) {
    const bien = await sinScrollHorizontal(w);
    ok(bien, `/panel${ruta} sin scroll horizontal a ${w}px`);
  }
  await pagina.setViewportSize({ width: 375, height: 800 });
  await pagina.screenshot({ path: `out/m${ruta.replaceAll("/", "-") || "-inicio"}.png` });
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
