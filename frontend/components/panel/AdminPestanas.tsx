"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const PESTANAS = [
  { href: "/panel/administracion", etiqueta: "Cuenta y usuarios" },
  { href: "/panel/administracion/impresora", etiqueta: "Impresora" },
  { href: "/panel/administracion/conexion", etiqueta: "Conexión" },
];

/** Pestañas de Administración (cada una es una página, así se puede abrir directo). */
export function AdminPestanas() {
  const ruta = usePathname();
  return (
    <nav className="pestanas-admin" aria-label="Secciones de Administración">
      {PESTANAS.map((p) => (
        <Link key={p.href} className="pestanas-admin__op" href={p.href} aria-current={ruta === p.href ? "page" : undefined}>
          {p.etiqueta}
        </Link>
      ))}
    </nav>
  );
}
