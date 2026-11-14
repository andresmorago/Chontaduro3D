"use client";

import Link from "next/link";
import { dinero, diaCorto, fechaLarga } from "@/lib/format";
import { api } from "@/lib/api";
import { useCargar } from "@/lib/hooks";

export default function Inicio() {
  const { datos: p, error, cargando } = useCargar(api.panel);

  if (cargando) return <p className="muted" role="status">Cargando…</p>;
  if (error || !p) return <p className="alerta" role="alert">{error ?? "No se pudo cargar el resumen."}</p>;

  const maximo = Math.max(...p.ultimos_dias.map((d) => d.total), 1);

  return (
    <>
      <div className="pagina-cab">
        <p className="code muted">{fechaLarga(p.hoy.fecha)}</p>
        <h1>Hoy</h1>
        <div className="pagina-cab__acciones">
          <Link className="btn btn--accent" href="/panel/vender">Registrar venta</Link>
          <Link className="btn btn--secondary" href="/panel/produccion">Sumar producción</Link>
        </div>
      </div>

      <div className="estadisticas">
        <div className="dato">
          <span className="dato__etiqueta">Vendido hoy</span>
          <span className="dato__valor">{dinero(p.hoy.total)}</span>
          <span className="dato__nota">{p.hoy.cantidad === 1 ? "1 venta" : `${p.hoy.cantidad} ventas`}</span>
        </div>
        <div className="dato">
          <span className="dato__etiqueta">Piezas en inventario</span>
          <span className="dato__valor">{p.unidades_en_stock}</span>
          <span className="dato__nota">{p.articulos_activos === 1 ? "1 artículo activo" : `${p.articulos_activos} artículos activos`}</span>
        </div>
        <Link className="dato" href="/panel/pedidos" style={{ textDecoration: "none" }}>
          <span className="dato__etiqueta">Pedidos nuevos</span>
          <span className="dato__valor">{p.pedidos_nuevos}</span>
          <span className="dato__nota">{p.pedidos_nuevos > 0 ? "Por contestar →" : "Todo al día"}</span>
        </Link>
      </div>

      <div className="dos-paneles">
      <section className="seccion" aria-labelledby="t-semana">
        <h2 id="t-semana">Ventas de los últimos 7 días</h2>
        {p.ultimos_dias.every((d) => d.total === 0) ? (
          <div className="vacio">
            <p>Todavía no hay ventas esta semana. Cuando registres una, aparece aquí.</p>
          </div>
        ) : (
          <div className="barras" role="img" aria-label={`Ventas por día: ${p.ultimos_dias.map((d) => `${diaCorto(d.fecha)} ${dinero(d.total)}`).join(", ")}`}>
            {p.ultimos_dias.map((d, i) => (
              <div key={d.fecha} className={`barra-dia${d.total === 0 ? " barra-dia--vacio" : ""}${i === p.ultimos_dias.length - 1 ? " barra-dia--hoy" : ""}`}>
                <div className="barra-dia__col" style={{ height: `${(d.total / maximo) * 100}%` }} />
                <span>{diaCorto(d.fecha)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="seccion" aria-labelledby="t-bajo">
        <h2 id="t-bajo">Por reponer</h2>
        {p.stock_bajo.length === 0 ? (
          <div className="vacio">
            <p>Ningún artículo está en su mínimo. Define el stock mínimo de cada artículo para recibir avisos aquí.</p>
          </div>
        ) : (
          <div className="lista">
            {p.stock_bajo.map((s) => (
              <Link key={s.articulo_id} href="/panel/produccion" className="fila fila--sin-foto" style={{ textDecoration: "none" }}>
                <span className="fila__titulo">
                  <span className="code muted">{s.codigo}</span>
                  <span className="fila__nombre">{s.nombre}</span>
                </span>
                <span className="fila__fin">
                  <span className={`stock-num ${s.stock === 0 ? "stock-num--cero" : "stock-num--bajo"}`}>{s.stock}</span>
                  <span className="fila__meta">mínimo {s.stock_minimo}</span>
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>
      </div>
    </>
  );
}
