"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Boton } from "@/components/ui/Boton";
import { Hoja } from "@/components/ui/Hoja";
import { Icono, type NombreIcono } from "@/components/ui/Icono";
import { ErrorApi, alSesionVencida, api } from "@/lib/api";
import type { Usuario } from "@/lib/types";

interface Contexto {
  usuario: Usuario | null;
  nuevos: number;
  refrescarNuevos: () => void;
}
const Ctx = createContext<Contexto>({ usuario: null, nuevos: 0, refrescarNuevos: () => {} });
export const usePanel = () => useContext(Ctx);

const DESTINOS: { href: string; etiqueta: string; corta: string; icono: NombreIcono }[] = [
  { href: "/panel", etiqueta: "Inicio", corta: "Inicio", icono: "inicio" },
  { href: "/panel/vender", etiqueta: "Vender", corta: "Vender", icono: "vender" },
  { href: "/panel/produccion", etiqueta: "Producción", corta: "Producir", icono: "producir" },
  { href: "/panel/inventario", etiqueta: "Inventario", corta: "Stock", icono: "stock" },
  { href: "/panel/articulos", etiqueta: "Artículos", corta: "Artículos", icono: "articulos" },
  { href: "/panel/pedidos", etiqueta: "Pedidos", corta: "Pedidos", icono: "pedidos" },
];
const PESTANAS = ["/panel/vender", "/panel/produccion", "/panel/inventario", "/panel/pedidos"];

export function PanelShell({ children }: { children: ReactNode }) {
  const ruta = usePathname();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [nuevos, setNuevos] = useState(0);
  const [menu, setMenu] = useState(false);

  const refrescarNuevos = useCallback(() => {
    api.panel().then((p) => setNuevos(p.pedidos_nuevos)).catch(() => {});
  }, []);

  useEffect(() => {
    alSesionVencida(() => window.location.assign("/entrar"));
    api.auth
      .yo()
      .then(setUsuario)
      // Solo un 401 real manda al login; un fallo de red pasajero no debe sacar a nadie de su sesión.
      .catch((e) => e instanceof ErrorApi && e.status === 401 && window.location.assign("/entrar"));
    return () => alSesionVencida(null);
  }, []);

  useEffect(() => {
    refrescarNuevos();
  }, [ruta, refrescarNuevos]);

  async function salir() {
    try {
      await api.auth.salir();
    } finally {
      window.location.assign("/entrar");
    }
  }

  const activa = (href: string) => (href === "/panel" ? ruta === "/panel" : ruta.startsWith(href));
  const valor = useMemo(() => ({ usuario, nuevos, refrescarNuevos }), [usuario, nuevos, refrescarNuevos]);
  const Insignia = ({ href }: { href: string }) => (href === "/panel/pedidos" && nuevos > 0 ? <span className="contador-nuevos" aria-label={`${nuevos} pedidos nuevos`}>{nuevos}</span> : null);

  return (
    <Ctx.Provider value={valor}>
      <div className="panel">
        <aside className="rail" aria-label="Menú del negocio">
          <Link className="rail__marca" href="/panel">
            Mis impresiones
          </Link>
          <nav className="rail__nav" aria-label="Secciones">
            {DESTINOS.map((d) => (
              <Link key={d.href} className="rail__enlace" href={d.href} aria-current={activa(d.href) ? "page" : undefined}>
                <Icono nombre={d.icono} />
                {d.etiqueta}
                <Insignia href={d.href} />
              </Link>
            ))}
          </nav>
          <div className="rail__pie">
            <p className="rail__cuenta">{usuario?.email ?? "…"}</p>
            <a className="rail__enlace" href="/" target="_blank" rel="noopener noreferrer">
              <Icono nombre="ver" />
              Ver catálogo
            </a>
            <button type="button" className="rail__enlace" onClick={salir} style={{ background: "transparent", textAlign: "left", font: "inherit" }}>
              <Icono nombre="salir" />
              Salir
            </button>
          </div>
        </aside>

        <header className="tope">
          <Link href="/panel">Mis impresiones</Link>
        </header>

        <main id="contenido" className="panel__main">
          {children}
        </main>

        <nav className="pestanas" aria-label="Secciones">
          {PESTANAS.map((h) => {
            const d = DESTINOS.find((x) => x.href === h);
            if (!d) return null;
            return (
              <Link key={h} className="pestana" href={h} aria-current={activa(h) ? "page" : undefined}>
                <Icono nombre={d.icono} />
                {d.corta}
                <Insignia href={h} />
              </Link>
            );
          })}
          <button type="button" className="pestana" onClick={() => setMenu(true)} aria-haspopup="dialog">
            <Icono nombre="mas_menu" />
            Más
          </button>
        </nav>
      </div>

      <Hoja abierta={menu} onCerrar={() => setMenu(false)} titulo="Más opciones" descripcion={usuario?.email}>
        <div style={{ display: "grid", gap: "var(--space-sm)" }}>
          <Link className="btn btn--secondary btn--block" href="/panel" onClick={() => setMenu(false)}>Inicio</Link>
          <Link className="btn btn--secondary btn--block" href="/panel/articulos" onClick={() => setMenu(false)}>Artículos</Link>
          <a className="btn btn--secondary btn--block" href="/" target="_blank" rel="noopener noreferrer">Ver catálogo público</a>
          <Boton variante="danger" bloque onClick={salir}>Salir</Boton>
        </div>
      </Hoja>
    </Ctx.Provider>
  );
}
