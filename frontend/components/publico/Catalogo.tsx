"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Boton } from "@/components/ui/Boton";
import { Foto } from "@/components/ui/Foto";
import { Icono } from "@/components/ui/Icono";
import { encuadreDe } from "@/lib/foto";
import { enlaceWhatsapp } from "@/lib/format";
import type { ArticuloPublico } from "@/lib/types";
import { useAvisos } from "@/components/ui/Avisos";
import { useCarrito } from "@/lib/carrito";
import { dinero } from "@/lib/format";
import { CarritoHoja } from "./CarritoHoja";
import { DetalleHoja } from "./DetalleHoja";

interface Props {
  articulos: ArticuloPublico[];
  whatsapp: string;
  sitekey: string;
  negocio: string;
}

const sinTildes = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export function Catalogo({ articulos, whatsapp, sitekey, negocio }: Props) {
  const [busqueda, setBusqueda] = useState("");
  const [elegido, setElegido] = useState<ArticuloPublico | null>(null);
  const [verPedido, setVerPedido] = useState(false);
  const { mostrar } = useAvisos();
  const carrito = useCarrito(articulos);

  function agregar(a: ArticuloPublico, color: string, cantidad: number) {
    carrito.agregar(a.id, color, cantidad);
    setElegido(null);
    mostrar(`Agregado: ${cantidad} × ${a.nombre}${color ? ` (${color})` : ""}`, { accion: { etiqueta: "Ver pedido", alPulsar: () => setVerPedido(true) } });
  }

  const visibles = useMemo(() => {
    const t = sinTildes(busqueda.trim());
    if (!t) return articulos;
    return articulos.filter((a) => sinTildes(`${a.nombre} ${a.codigo} ${a.descripcion}`).includes(t));
  }, [articulos, busqueda]);

  return (
    <>
      <header className="sitio-cab">
        <div className="container barra">
          <Link className="barra__marca" href="/">
            {negocio}
          </Link>
          <form className="buscar" role="search" onSubmit={(e) => e.preventDefault()}>
            <label className="visually-hidden" htmlFor="buscar">
              Buscar en el catálogo
            </label>
            <input id="buscar" className="input" type="search" placeholder="Buscar por nombre o código" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} autoComplete="off" />
            <Boton variante="primary" type="submit" aria-label="Buscar">
              <Icono nombre="buscar" />
            </Boton>
          </form>
          {carrito.piezas > 0 && (
            <Boton variante="accent" className="barra__pedido" onClick={() => setVerPedido(true)} aria-label={`Mi pedido: ${carrito.piezas} ${carrito.piezas === 1 ? "pieza" : "piezas"}`}>
              Mi pedido <span className="barra__cuenta">{carrito.piezas}</span>
            </Boton>
          )}
          {whatsapp && (
            <a className="btn btn--secondary barra__wa" href={enlaceWhatsapp(whatsapp, `Hola ${negocio}, quisiera hacer una consulta.`)} target="_blank" rel="noopener noreferrer">
              WhatsApp
            </a>
          )}
        </div>
      </header>

      <main id="contenido">
        <section className="container catalogo-cab" aria-labelledby="titulo-catalogo">
          <h1 id="titulo-catalogo">Piezas impresas en 3D</h1>
          <p className="lead">Mira lo que hay, elige y déjanos tu pedido. Te escribimos por WhatsApp para confirmarlo.</p>
          <p className="catalogo-cab__cuenta">
            {articulos.length === 1 ? "1 artículo" : `${articulos.length} artículos`} · Toca uno para ver el detalle, el precio y los colores
          </p>
        </section>

        <section className="container" aria-label="Artículos">
          {articulos.length === 0 ? (
            <div className="vacio">
              <h2 style={{ fontSize: "var(--text-title)" }}>Aún no hay artículos publicados</h2>
              <p>Estamos preparando el catálogo. Vuelve pronto o escríbenos por WhatsApp.</p>
            </div>
          ) : visibles.length === 0 ? (
            <div className="vacio">
              <h2 style={{ fontSize: "var(--text-title)" }}>No encontré «{busqueda}»</h2>
              <p>Prueba con otra palabra o con el código del artículo.</p>
              <Boton variante="secondary" onClick={() => setBusqueda("")}>
                Ver todo
              </Boton>
            </div>
          ) : (
            <ul className="catalogo" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {visibles.map((a) => (
                <li key={a.id} className="articulo">
                  <button type="button" className="articulo__boton" onClick={() => setElegido(a)} aria-label={`Ver ${a.nombre}`}>
                    <Foto url={a.imagen_url} codigo={a.codigo} nombre="" clase="articulo__foto" enc={encuadreDe(a)} />
                    <span className="articulo__nombre">{a.nombre}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>

      <footer className="sitio-pie">
        <div className="container pie-mast">
          <p className="pie-mast__marca">{negocio}</p>
          <p className="muted">Piezas impresas en 3D.</p>
          <p className="pie-mast__enlaces">
            {whatsapp && (
              <a href={enlaceWhatsapp(whatsapp, `Hola ${negocio}, quisiera hacer una consulta.`)} target="_blank" rel="noopener noreferrer">
                Escríbenos por WhatsApp
              </a>
            )}
            <a href="/entrar">Acceso del negocio</a>
          </p>
        </div>
      </footer>

      <DetalleHoja articulo={elegido} onCerrar={() => setElegido(null)} onAgregar={agregar} carritoLleno={carrito.lleno && !carrito.lineas.some((l) => l.articuloId === elegido?.id)} />
      <CarritoHoja abierta={verPedido} lineas={carrito.lineas} total={carrito.total} piezas={carrito.piezas} sitekey={sitekey} onCerrar={() => setVerPedido(false)} onCambiar={carrito.poner} onEnviado={carrito.vaciar} />
      {carrito.piezas > 0 && !verPedido && (
        <div className="carrito-barra">
          <div className="container carrito-barra__dentro">
            <span>
              <strong className="num">{carrito.piezas === 1 ? "1 pieza" : `${carrito.piezas} piezas`}</strong> · {dinero(carrito.total)}
            </span>
            <Boton variante="accent" onClick={() => setVerPedido(true)}>
              Ver mi pedido
            </Boton>
          </div>
        </div>
      )}
    </>
  );
}
