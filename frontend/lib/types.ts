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
  desde_impresora: string | null;
}

export interface ExtraProduccion {
  trabajo_id?: string;
  fecha?: string;
  afecta_inventario?: boolean;
  precio_kwh?: number;
  potencia_w?: number;
  gramos_total?: number;
  filamentos?: Filamento[];
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
  nube: NubeConexion;
}

export interface PasoNube {
  paso: "listo" | "codigo" | "tfa";
  tfa_key: string | null;
}

export type ComandoImpresora = "pausar" | "reanudar" | "cancelar" | "luz" | "velocidad" | "temp_boquilla" | "temp_cama" | "ventilador_pieza" | "ventilador_aux";

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
  gramos_total: number | null;
  filamentos: FilamentoTrabajo[];
  produccion_id: string | null;
}
