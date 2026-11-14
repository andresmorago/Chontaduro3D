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
  nombre: string;
  hex: string;
}

export interface Articulo {
  id: string;
  codigo: string;
  nombre: string;
  descripcion: string;
  imagen_url: string | null;
  precio_venta: number;
  stock_minimo: number;
  stock: number;
  publicado: boolean;
  activo: boolean;
  colores: Color[];
}

export interface ArticuloEntrada {
  nombre: string;
  descripcion: string;
  precio_venta: number;
  stock_minimo: number;
  publicado: boolean;
  colores: Color[];
}

export interface PrecioHistorial {
  precio: number;
  cambiado_en: string;
}

export interface ItemCantidad {
  articulo_id: string;
  cantidad: number;
}

export interface ProduccionItem {
  articulo_id: string;
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
}

export interface VentaItem {
  articulo_id: string;
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
}

export interface Movimiento {
  id: number;
  articulo_id: string;
  codigo: string;
  nombre: string;
  tipo: "produccion" | "venta" | "ajuste" | "anulacion";
  cantidad: number;
  nota: string | null;
  creado_en: string;
}

export interface Pedido {
  id: string;
  articulo_id: string;
  codigo: string;
  articulo: string;
  nombre: string;
  whatsapp: string;
  cantidad: number;
  color: string | null;
  estado: EstadoPedido;
  creado_en: string;
}

export interface ArticuloPublico {
  id: string;
  codigo: string;
  nombre: string;
  descripcion: string;
  imagen_url: string | null;
  precio: number;
  disponible: boolean;
  colores: Color[];
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
  color: string | null;
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
  luz: "on" | "off" | null;
  wifi: string | null;
  error: number;
  alertas: number;
  ams: BandejaAms[];
  externa: BandejaAms | null;
}

export interface Impresora {
  servicio_activo: boolean;
  conectada: boolean;
  actualizado_en: string | null;
  datos: DatosImpresora | null;
  trabajos_pendientes: number;
}

export type ComandoImpresora = "pausar" | "reanudar" | "cancelar" | "luz" | "velocidad";

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
  gramos_total: number | null;
  filamentos: FilamentoTrabajo[];
  produccion_id: string | null;
}
