// Iconos de trazo, dibujados aquí: sin librería y sin emojis.
const RUTAS = {
  mas: "M12 5v14M5 12h14",
  menos: "M5 12h14",
  buscar: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
  cerrar: "M6 6l12 12M18 6L6 18",
  inicio: "M4 11l8-7 8 7M6 10v10h12V10",
  vender: "M5 7h14l-1.5 11h-11zM9 7a3 3 0 0 1 6 0",
  producir: "M4 20h16M7 20V10l5-6 5 6v10M10 20v-5h4v5",
  stock: "M4 7l8-4 8 4v10l-8 4-8-4zM4 7l8 4 8-4M12 11v10",
  articulos: "M5 4h14v16H5zM9 9h6M9 13h6M9 17h3",
  pedidos: "M4 5h16v11H9l-5 4zM8 9h8M8 12h5",
  salir: "M10 4H5v16h5M15 8l4 4-4 4M19 12H9",
  ver: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  whatsapp: "M4 20l1.4-4.2A8 8 0 1 1 8.2 18.6zM9 9c0 3 3 6 6 6l1-1.5-2-1-1 .8c-.8-.4-1.6-1.2-2-2l.8-1-1-2z",
  mas_menu: "M5 12h.01M12 12h.01M19 12h.01",
  editar: "M4 20h4L19 9l-4-4L4 16zM13 7l4 4",
  foto: "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M9 9h.01",
  check: "M5 12l5 5 9-10",
} as const;

export type NombreIcono = keyof typeof RUTAS;

export function Icono({ nombre, tamano = 20 }: { nombre: NombreIcono; tamano?: number }) {
  return (
    <svg width={tamano} height={tamano} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="square" strokeLinejoin="miter" aria-hidden="true" focusable="false">
      <path d={RUTAS[nombre]} />
    </svg>
  );
}
