// Cliente de la API. Un solo origen: el navegador llama a `/api/*` (Next lo reenvía al
// backend). Las cookies de sesión son httpOnly: aquí no hay tokens que guardar.
// En el servidor (componentes de servidor) se llama directo a la red interna.

import type {
  Articulo,
  ArticuloEntrada,
  CatalogoPublico,
  ComandoImpresora,
  ConfigPublica,
  EstadoPedido,
  ExtraProduccion,
  Impresora,
  ItemCantidad,
  Movimiento,
  OrdenImpresora,
  Panel,
  Parametros,
  Pedido,
  PrecioHistorial,
  Produccion,
  TrabajoImpresora,
  Usuario,
  UsuarioAdmin,
  Venta,
  VentaEntrada,
} from "./types";

const EN_SERVIDOR = typeof window === "undefined";
const BASE = EN_SERVIDOR ? `${process.env.API_INTERNAL_URL ?? "http://backend:8000"}/api` : "/api";

export class ErrorApi extends Error {
  constructor(
    readonly status: number,
    mensaje: string,
  ) {
    super(mensaje);
    this.name = "ErrorApi";
  }
}

type Detalle = string | { msg?: string; loc?: (string | number)[] }[] | undefined;

function mensajeDe(status: number, detalle: Detalle): string {
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle) && detalle[0]?.msg) {
    const campo = detalle[0].loc?.filter((x) => typeof x === "string" && x !== "body").pop();
    return `Revisa los datos${campo ? ` (${campo})` : ""}: ${detalle[0].msg}`;
  }
  if (status === 429) return "Demasiados intentos. Espera un momento e inténtalo de nuevo.";
  if (status >= 500) return "Algo falló de nuestro lado. Inténtalo de nuevo en un momento.";
  return "No se pudo completar la acción.";
}

// Cuando la sesión no se puede renovar, el panel se entera por aquí y manda a /entrar.
let alVencerSesion: (() => void) | null = null;
export function alSesionVencida(fn: (() => void) | null) {
  alVencerSesion = fn;
}

// «ok»: sesión renovada · «vencida»: el servidor dijo 401 (hay que volver a entrar) ·
// «red»: no se pudo saber (sin conexión, petición interrumpida, error 5xx): NO es motivo para sacar al usuario.
type ResultadoRenovar = "ok" | "vencida" | "red";
let renovando: Promise<ResultadoRenovar> | null = null;
function renovarSesion(): Promise<ResultadoRenovar> {
  // Varias llamadas que fallan a la vez comparten una sola renovación (el token rota).
  renovando ??= fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "X-Requested-With": "fetch" },
    credentials: "same-origin",
  })
    .then((r): ResultadoRenovar => (r.ok ? "ok" : r.status === 401 ? "vencida" : "red"))
    .catch((): ResultadoRenovar => "red")
    .finally(() => {
      renovando = null;
    });
  return renovando;
}

interface Opciones {
  metodo?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  cuerpo?: unknown;
  formulario?: FormData;
  sinRenovar?: boolean;
}

async function pedir<T>(ruta: string, o: Opciones = {}): Promise<T> {
  const cabeceras: Record<string, string> = { "X-Requested-With": "fetch" };
  let body: BodyInit | undefined;
  if (o.formulario) body = o.formulario;
  else if (o.cuerpo !== undefined) {
    cabeceras["Content-Type"] = "application/json";
    body = JSON.stringify(o.cuerpo);
  }
  let r: Response;
  try {
    r = await fetch(`${BASE}${ruta}`, {
      method: o.metodo ?? "GET",
      headers: cabeceras,
      body,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new ErrorApi(0, "No hay conexión. Revisa tu internet e inténtalo de nuevo.");
  }

  if (r.status === 401 && !o.sinRenovar && !EN_SERVIDOR) {
    const estado = await renovarSesion();
    if (estado === "ok") return pedir<T>(ruta, { ...o, sinRenovar: true });
    if (estado === "vencida") alVencerSesion?.();
    else throw new ErrorApi(0, "No hay conexión. Revisa tu internet e inténtalo de nuevo.");
  }
  if (!r.ok) {
    let detalle: Detalle;
    try {
      detalle = ((await r.json()) as { detail?: Detalle }).detail;
    } catch {
      detalle = undefined;
    }
    throw new ErrorApi(r.status, mensajeDe(r.status, detalle));
  }
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

const q = (p: Record<string, string | number | boolean | undefined>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== "") s.set(k, String(v));
  const t = s.toString();
  return t ? `?${t}` : "";
};

export const api = {
  auth: {
    entrar: (email: string, password: string, turnstile = "") =>
      pedir<Usuario>("/auth/login", { metodo: "POST", cuerpo: { email, password, turnstile }, sinRenovar: true }),
    salir: () => pedir<void>("/auth/logout", { metodo: "POST", sinRenovar: true }),
    yo: () => pedir<Usuario>("/auth/yo"),
  },
  publico: {
    catalogo: () => pedir<CatalogoPublico>("/publico/articulos"),
    config: () => pedir<ConfigPublica>("/publico/config"),
    pedir: (d: { articulo_id: string; nombre: string; whatsapp: string; cantidad: number; color: string; sitio_web: string; turnstile: string }) =>
      pedir<{ ok: boolean; mensaje: string }>("/publico/pedidos", { metodo: "POST", cuerpo: d }),
  },
  impresora: {
    ver: () => pedir<Impresora>("/impresora"),
    ordenar: (comando: ComandoImpresora, valor?: string) =>
      pedir<OrdenImpresora>("/impresora/comandos", { metodo: "POST", cuerpo: { comando, valor: valor ?? null } }),
    orden: (id: number) => pedir<OrdenImpresora>(`/impresora/comandos/${id}`),
    trabajos: (gestion: TrabajoImpresora["gestion"] = "pendiente") => pedir<TrabajoImpresora[]>(`/impresora/trabajos${q({ gestion })}`),
    ignorar: (id: string) => pedir<TrabajoImpresora>(`/impresora/trabajos/${id}/ignorar`, { metodo: "POST" }),
    restaurar: (id: string) => pedir<TrabajoImpresora>(`/impresora/trabajos/${id}/restaurar`, { metodo: "POST" }),
  },
  panel: () => pedir<Panel>("/panel"),
  usuarios: {
    listar: () => pedir<UsuarioAdmin[]>("/usuarios"),
    crear: (d: { nombre: string; email: string; password: string }) =>
      pedir<UsuarioAdmin>("/usuarios", { metodo: "POST", cuerpo: d }),
    actualizar: (id: string, d: { nombre?: string; activo?: boolean }) =>
      pedir<UsuarioAdmin>(`/usuarios/${id}`, { metodo: "PATCH", cuerpo: d }),
    restablecer: (id: string, nueva: string) =>
      pedir<void>(`/usuarios/${id}/contrasena`, { metodo: "POST", cuerpo: { nueva } }),
    cambiarMia: (actual: string, nueva: string) =>
      pedir<void>("/usuarios/yo/contrasena", { metodo: "POST", cuerpo: { actual, nueva } }),
  },
  parametros: {
    ver: () => pedir<Parametros>("/parametros"),
    guardar: (d: Parametros) => pedir<Parametros>("/parametros", { metodo: "PUT", cuerpo: d }),
  },
  articulos: {
    listar: (incluirInactivos = false) =>
      pedir<Articulo[]>(`/articulos${q({ incluir_inactivos: incluirInactivos || undefined })}`),
    crear: (d: ArticuloEntrada) => pedir<Articulo>("/articulos", { metodo: "POST", cuerpo: d }),
    actualizar: (id: string, d: Partial<ArticuloEntrada> & { activo?: boolean }) =>
      pedir<Articulo>(`/articulos/${id}`, { metodo: "PATCH", cuerpo: d }),
    precios: (id: string) => pedir<PrecioHistorial[]>(`/articulos/${id}/precios`),
    subirImagen: (id: string, archivo: File) => {
      const f = new FormData();
      f.append("archivo", archivo);
      return pedir<Articulo>(`/articulos/${id}/imagen`, { metodo: "PUT", formulario: f });
    },
    quitarImagen: (id: string) => pedir<Articulo>(`/articulos/${id}/imagen`, { metodo: "DELETE" }),
    subirImagenColor: (id: string, colorId: string, archivo: File) => {
      const f = new FormData();
      f.append("archivo", archivo);
      return pedir<Articulo>(`/articulos/${id}/colores/${colorId}/imagen`, { metodo: "PUT", formulario: f });
    },
    quitarImagenColor: (id: string, colorId: string) => pedir<Articulo>(`/articulos/${id}/colores/${colorId}/imagen`, { metodo: "DELETE" }),
  },
  produccion: {
    listar: (limite = 30) => pedir<Produccion[]>(`/produccion${q({ limite })}`),
    registrar: (items: ItemCantidad[], nota?: string, extra: ExtraProduccion = {}) =>
      pedir<Produccion>("/produccion", { metodo: "POST", cuerpo: { items, nota: nota || null, ...extra } }),
    modificar: (id: string, items: ItemCantidad[], nota?: string, extra: ExtraProduccion = {}) =>
      pedir<Produccion>(`/produccion/${id}`, { metodo: "PUT", cuerpo: { items, nota: nota || null, ...extra } }),
  },
  ventas: {
    deHoy: () => pedir<Venta[]>("/ventas"),
    registrar: (d: VentaEntrada) => pedir<Venta>("/ventas", { metodo: "POST", cuerpo: d }),
    anular: (id: string) => pedir<Venta>(`/ventas/${id}/anular`, { metodo: "POST" }),
  },
  inventario: {
    existencias: () => pedir<Articulo[]>("/inventario"),
    movimientos: (articuloId?: string) =>
      pedir<Movimiento[]>(`/inventario/movimientos${q({ articulo_id: articuloId, limite: 30 })}`),
    ajustar: (articulo_id: string, cantidad: number, nota: string) =>
      pedir<Articulo>("/inventario/ajustes", { metodo: "POST", cuerpo: { articulo_id, cantidad, nota } }),
  },
  pedidos: {
    listar: (estado?: EstadoPedido) => pedir<Pedido[]>(`/pedidos${q({ estado })}`),
    cambiarEstado: (id: string, estado: EstadoPedido) =>
      pedir<Pedido>(`/pedidos/${id}`, { metodo: "PATCH", cuerpo: { estado } }),
  },
};
