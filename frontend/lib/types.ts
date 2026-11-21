// Espejo de los esquemas de la API (backend/app/schemas/dominio.py).

export type MetodoPago = "efectivo" | "transferencia" | "otro";
export type EstadoPedido = "nuevo" | "contactado" | "cerrado" | "descartado";

export interface Usuario {
  id: string;
  email: string;
  nombre?: string | null;
}

export interface UsuarioAdmin {
  id: string;
  email: string;
  nombre: string | null;
  activo: boolean;
  creado_en: string;
  es_yo: boolean;
}

export interface Color {
  id: string;
  nombre: string;
  hex: string;
  imagen_url: string | null;
  foto_x: number;
  foto_y: number;
  foto_zoom: number;
}

/** Un color tal como se envía al guardar un artículo (con `id` = uno que ya existe). */
export interface ColorEntrada {
  id?: string;
  nombre: string;
  hex: string;
  foto_x: number;
  foto_y: number;
  foto_zoom: number;
}

/** Stock de un color de un artículo (`color_id` null = «sin color asignado», anterior a los colores). */
export interface StockColor {
  color_id: string | null;
  nombre: string | null;
  hex: string | null;
  stock: number;
}

export interface Articulo {
  id: string;
  codigo: string;
  nombre: string;
  descripcion: string;
  imagen_url: string | null;
  foto_x: number;
  foto_y: number;
  foto_zoom: number;
  precio_venta: number;
  stock_minimo: number;
  stock: number;
  publicado: boolean;
  activo: boolean;
  colores: Color[];
  /** Solo en artículos con colores. */
  stock_colores: StockColor[];
}

export interface ArticuloEntrada {
  nombre: string;
  descripcion: string;
  precio_venta: number;
  stock_minimo: number;
  publicado: boolean;
  foto_x: number;
  foto_y: number;
  foto_zoom: number;
  colores: ColorEntrada[];
}

export interface PrecioHistorial {
  precio: number;
  cambiado_en: string;
}

export interface ItemCantidad {
  articulo_id: string;
  /** Obligatorio si el artículo tiene colores. */
  color_id?: string;
  cantidad: number;
}

export interface ProduccionItem {
  articulo_id: string;
  color_id: string | null;
  color: string | null;
  color_hex: string | null;
  codigo: string;
  nombre: string;
  cantidad: number;
}

export interface Filamento {
  descripcion: string;
  gramos: number;
  /** Bobina de Spoolman de la que salió (opcional). */
  spool_id?: number | null;
  /** Nombre y color ACTUALES de esa bobina en Spoolman; si faltan, vale `descripcion`. */
  bobina?: string | null;
  /** Costo de la línea, congelado al guardar el lote (null si no hay bobina con precio). */
  costo?: number | null;
  color?: string | null;
}

/** Lo que se manda al guardar una línea de filamento. Con bobina, el texto puede ir vacío. */
export interface FilamentoEntrada {
  descripcion: string;
  gramos: number;
  spool_id?: number;
}

export interface Produccion {
  id: string;
  fecha: string;
  nota: string | null;
  creado_en: string;
  items: ProduccionItem[];
  afecta_inventario: boolean;
  gramos_total: number | null;
  filamentos: Filamento[];
  minutos_impresion: number | null;
  potencia_w: number | null;
  precio_kwh: number | null;
  kwh: number | null;
  costo_energia: number | null;
  /** Filamento del lote: suma de las líneas con costo; «parcial» = a alguna línea le falta el precio. */
  costo_filamento: number | null;
  costo_filamento_parcial: boolean;
  desde_impresora: string | null;
}

export interface ExtraProduccion {
  trabajo_id?: string;
  fecha?: string;
  afecta_inventario?: boolean;
  precio_kwh?: number;
  potencia_w?: number;
  gramos_total?: number;
  filamentos?: FilamentoEntrada[];
  minutos_impresion?: number;
}

export interface Parametros {
  precio_kwh: number | null;
  potencia_impresora_w: number | null;
}

export interface VentaItemEntrada extends ItemCantidad {
  precio_unitario?: number;
}

export interface VentaEntrada {
  fecha?: string;
  cliente?: string;
  metodo_pago: MetodoPago;
  nota?: string;
  items: VentaItemEntrada[];
  /** Asocia la venta a un pedido; con `cerrar_pedido` el pedido pasa a «cerrado». */
  pedido_id?: string;
  cerrar_pedido?: boolean;
}

export interface VentaItem {
  articulo_id: string;
  color_id: string | null;
  color: string | null;
  color_hex: string | null;
  codigo: string;
  nombre: string;
  cantidad: number;
  precio_unitario: number;
}

export interface Venta {
  id: string;
  fecha: string;
  cliente: string | null;
  metodo_pago: MetodoPago;
  nota: string | null;
  total: number;
  anulada: boolean;
  creado_en: string;
  items: VentaItem[];
  /** Pedido del catálogo que esta venta atendió (opcional). */
  pedido_id: string | null;
  pedido_nombre: string | null;
}

/** Un día del calendario de ventas: ventas vigentes (sin anuladas) y su total. */
export interface VentaDia {
  fecha: string;
  ventas: number;
  total: number;
}

export interface Movimiento {
  id: number;
  articulo_id: string;
  codigo: string;
  nombre: string;
  tipo: "produccion" | "venta" | "ajuste" | "anulacion";
  cantidad: number;
  color: string | null;
  nota: string | null;
  creado_en: string;
}

export interface PedidoItem {
  articulo_id: string;
  codigo: string;
  articulo: string;
  color: string | null;
  cantidad: number;
  /** Precio de hoy del artículo (referencia: el precio final se acuerda al vender). */
  precio: number;
  subtotal: number;
}

/** Una venta que atendió un pedido. */
export interface PedidoVenta {
  id: string;
  fecha: string;
  total: number;
  anulada: boolean;
}

/** Lo pendiente de un color de un artículo en los pedidos por atender. */
export interface DemandaColor {
  color: string | null;
  pendiente: number;
  stock: number;
  faltan: number;
}

/** Lo que piden los pedidos por atender de un artículo, contra el stock. */
export interface DemandaArticulo {
  articulo_id: string;
  codigo: string;
  articulo: string;
  /** Pedidos abiertos que lo piden. */
  pedidos: number;
  /** Piezas pedidas que aún no se han vendido. */
  pendiente: number;
  stock: number;
  /** Lo que hay que producir para cubrirlo. */
  faltan: number;
  colores: DemandaColor[];
}

export interface Pedido {
  id: string;
  nombre: string;
  whatsapp: string;
  items: PedidoItem[];
  piezas: number;
  total_estimado: number;
  estado: EstadoPedido;
  creado_en: string;
  ventas: PedidoVenta[];
  /** Lo vendido a este pedido, sin contar las ventas anuladas. */
  total_vendido: number;
}

/** Un color en el catálogo público: solo «hay / no hay», nunca la cifra. */
export interface ColorPublico {
  id: string;
  nombre: string;
  hex: string;
  imagen_url: string | null;
  foto_x: number;
  foto_y: number;
  foto_zoom: number;
  disponible: boolean;
}

export interface ArticuloPublico {
  id: string;
  codigo: string;
  nombre: string;
  descripcion: string;
  imagen_url: string | null;
  foto_x: number;
  foto_y: number;
  foto_zoom: number;
  precio: number;
  disponible: boolean;
  colores: ColorPublico[];
}

export interface CatalogoPublico {
  articulos: ArticuloPublico[];
  whatsapp_negocio: string;
  turnstile_sitekey: string;
}

export interface ConfigPublica {
  turnstile_sitekey: string;
}

export interface VentasDia {
  fecha: string;
  total: number;
  cantidad: number;
}

export interface StockBajo {
  articulo_id: string;
  codigo: string;
  nombre: string;
  stock: number;
  stock_minimo: number;
}

export interface Panel {
  hoy: VentasDia;
  ultimos_dias: VentasDia[];
  stock_bajo: StockBajo[];
  pedidos_nuevos: number;
  articulos_activos: number;
  unidades_en_stock: number;
}

// --- Impresora 3D (Bambu Lab A1) ---------------------------------------------
export interface BandejaAms {
  id: string;
  vacia: boolean;
  tipo: string | null;
  marca: string | null;
  color: string | null;
  medido: boolean;
  restante: number | null;
  en_uso: boolean;
}

export type EstadoMaquina = "lista" | "preparando" | "imprimiendo" | "pausada" | "terminada" | "fallida" | "desconocido";

export interface DatosImpresora {
  estado: EstadoMaquina;
  trabajo: string | null;
  progreso: number | null;
  capa: number | null;
  capas: number | null;
  restante_min: number | null;
  boquilla: number | null;
  boquilla_objetivo: number | null;
  cama: number | null;
  cama_objetivo: number | null;
  boquilla_mm: string | null;
  velocidad: number | null;
  ventilador_pieza: number | null;
  ventilador_aux: number | null;
  luz: "on" | "off" | null;
  wifi: string | null;
  error: number;
  alertas: number;
  ams: BandejaAms[];
  externa: BandejaAms | null;
}

export interface NubeBambu {
  estado: "sin_configurar" | "ok" | "requiere_login" | "error" | null;
  sincronizada_en: string | null;
  detalle: string | null;
}

export interface Impresora {
  servicio_activo: boolean;
  nube: NubeBambu;
  conectada: boolean;
  actualizado_en: string | null;
  datos: DatosImpresora | null;
  trabajos_pendientes: number;
}

// --- Administración → Conexión (impresora y cuenta de Bambu Cloud) ---------------
export interface NubeConexion {
  vinculada: boolean;
  correo: string | null;
  estado: NubeBambu["estado"];
  sincronizada_en: string | null;
  detalle: string | null;
  /** Se pidió sincronizar y el servicio aún no lo atendió. */
  pendiente: boolean;
}

export interface ConexionImpresora {
  ip: string | null;
  serial: string | null;
  codigo_guardado: boolean;
  /** Hay datos guardados pero no se pueden leer (cambió SECRET_KEY): hay que escribirlos otra vez. */
  ilegible: boolean;
  servicio_activo: boolean;
  conectada: boolean;
  /** Se guardó un cambio y el servicio aún no reconectó con él. */
  pendiente: boolean;
  error: "credenciales" | "red" | null;
  /** Cuándo respondió la impresora por última vez y qué hace: la prueba de que está en línea. */
  ultimo_mensaje_en: string | null;
  maquina: string | null;
  nube: NubeConexion;
}

export interface PasoNube {
  paso: "listo" | "codigo" | "tfa";
  tfa_key: string | null;
}

export type ComandoImpresora = "pausar" | "reanudar" | "cancelar" | "luz" | "velocidad" | "temp_boquilla" | "temp_cama" | "ventilador_pieza" | "ventilador_aux" | "leer_rfid";

export interface OrdenImpresora {
  id: number;
  comando: ComandoImpresora;
  valor: string | null;
  estado: "pendiente" | "enviado" | "fallido" | "vencido";
  detalle: string | null;
}

export interface FilamentoTrabajo {
  tipo: string;
  color: string | null;
  gramos: number;
}

export interface TrabajoImpresora {
  id: string;
  nombre: string;
  estado: "en_curso" | "terminado" | "interrumpido";
  gestion: "pendiente" | "importado" | "ignorado";
  inicio_en: string;
  fin_en: string | null;
  fecha: string;
  progreso: number;
  minutos: number | null;
  minutos_origen: "medido" | "estimado" | null;
  minutos_estimados: number | null;
  origen: "impresora" | "nube";
  /** «web»: enviado desde Bambu Studio/Handy; «impresora»: lanzado desde su pantalla; null: aún sin saber. */
  desde: "web" | "impresora" | null;
  gramos_total: number | null;
  filamentos: FilamentoTrabajo[];
  produccion_id: string | null;
  /** Descuento de filamento en Spoolman, por filamento. */
  consumos: ConsumoFilamento[];
}

// --- Spoolman (inventario de bobinas) ------------------------------------------------
export interface EstadoSpoolman {
  configurado: boolean;
  conectado: boolean;
  version: string | null;
  ultimo_ok_en: string | null;
  detalle: string | null;
  /** Enlace para abrir Spoolman desde la red de casa. */
  url_web: string | null;
  /** Descuentos que esperan una decisión. */
  por_resolver: number;
  /** Las bobinas Bambu con chip se registran solas en Spoolman al verlas en el AMS. */
  autoregistro: boolean;
}

export interface BobinaSpoolman {
  id: number;
  nombre: string;
  material: string | null;
  color: string | null;
  restante_g: number | null;
  inicial_g: number | null;
  ubicacion: string | null;
  precio: number | null;
  /** Queda menos del umbral: hay que ir pensando en otro rollo. */
  bajo: boolean;
}

export interface RepuestosSpoolman {
  umbral_g: number;
  bobinas: BobinaSpoolman[];
}

export type EstadoAlcance = "alcanza" | "justo" | "no_alcanza" | "dudoso" | "sin_bobina" | "sin_peso";

export interface LineaAlcance {
  tipo: string | null;
  color: string | null;
  gramos: number;
  ranura: string | null;
  ranura_nombre: string | null;
  bobina: string | null;
  restante_g: number | null;
  estado: EstadoAlcance;
}

export interface AlcanceTrabajo {
  trabajo: string | null;
  leyendo: boolean;
  lineas: LineaAlcance[];
  alerta: boolean;
}

export interface VinculoRanura {
  /** «rfid»: el chip de la bobina Bambu está vinculado en Spoolman; «manual»: elegida a mano para la ranura. */
  tipo: "rfid" | "manual";
  /** «desactualizado»: la ranura cambió de tipo o color desde que se vinculó. */
  estado: "ok" | "desactualizado" | "sin_vincular";
  bobina: BobinaSpoolman | null;
}

export interface RanuraSpoolman {
  ranura: string;
  nombre: string;
  tipo: string | null;
  marca: string | null;
  color: string | null;
  en_uso: boolean;
  /** UID del chip RFID que la impresora leyó en esta ranura (null = sin chip o aún no lo lee). */
  tag: string | null;
  vinculo: VinculoRanura;
}

export type EstadoConsumo = "sin_bobina" | "por_enviar" | "enviando" | "descontado" | "omitido" | "revisar";

export interface ConsumoFilamento {
  id: string;
  trabajo_id: string;
  trabajo: string | null;
  fecha: string | null;
  orden: number;
  tipo: string | null;
  color: string | null;
  gramos_plan: number;
  gramos: number;
  ranura: string | null;
  spool_id: number | null;
  estado: EstadoConsumo;
  detalle: string | null;
  descontado_en: string | null;
}

export type AccionConsumo = "asignar" | "omitir" | "reintentar" | "confirmar";
