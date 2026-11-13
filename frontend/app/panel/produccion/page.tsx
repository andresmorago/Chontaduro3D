"use client";

import { useState } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { Contador } from "@/components/ui/Contador";
import { Entrada } from "@/components/ui/Campo";
import { Selector } from "@/components/panel/Selector";
import { api } from "@/lib/api";
import { fechaHora } from "@/lib/format";
import { mensajeDe, useCargar } from "@/lib/hooks";
import type { Articulo } from "@/lib/types";

export default function Produccion() {
  const { mostrar } = useAvisos();
  const articulos = useCargar(() => api.articulos.listar());
  const historial = useCargar(api.produccion.listar);
  const [cantidades, setCantidades] = useState<Record<string, number>>({});
  const [nota, setNota] = useState("");
  const [enviando, setEnviando] = useState(false);

  const lista = articulos.datos ?? [];
  const porId = new Map(lista.map((a) => [a.id, a]));
  const items = Object.entries(cantidades).filter(([id, n]) => n > 0 && porId.has(id));
  const unidades = items.reduce((s, [, n]) => s + n, 0);

  const tocar = (a: Articulo) => setCantidades((m) => ({ ...m, [a.id]: Math.min(10000, (m[a.id] ?? 0) + 1) }));
  const poner = (id: string, n: number) =>
    setCantidades((m) => {
      const { [id]: _q, ...resto } = m;
      void _q;
      return n <= 0 ? resto : { ...m, [id]: n };
    });

  async function registrar() {
    if (items.length === 0) return;
    setEnviando(true);
    try {
      await api.produccion.registrar(items.map(([articulo_id, cantidad]) => ({ articulo_id, cantidad })), nota.trim() || undefined);
      setCantidades({});
      setNota("");
      mostrar(unidades === 1 ? "Listo: 1 pieza entró al inventario." : `Listo: ${unidades} piezas entraron al inventario.`);
      await Promise.all([articulos.recargar(), historial.recargar()]);
    } catch (e) {
      mostrar(mensajeDe(e), { tipo: "error" });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <>
      <div className="pagina-cab">
        <h1>Producción</h1>
        <p className="lead">Toca lo que acabas de imprimir. Al guardar, suma al inventario.</p>
      </div>

      {articulos.error && <p className="alerta" role="alert">{articulos.error}</p>}
      {articulos.cargando ? (
        <p className="muted" role="status">Cargando artículos…</p>
      ) : lista.length === 0 ? (
        <div className="vacio">
          <h2 style={{ fontSize: "var(--text-title)" }}>Aún no hay artículos</h2>
          <p>Primero crea el artículo maestro; después registras cuántos imprimiste.</p>
          <a className="btn btn--primary" href="/panel/articulos">Crear artículo</a>
        </div>
      ) : (
        <div className="venta-grid">
          <Selector articulos={lista} cantidades={Object.fromEntries(items)} onTocar={tocar} />
          <section className="ticket" id="ticket" aria-labelledby="t-lote">
            <h2 id="t-lote" style={{ fontSize: "var(--text-title)" }}>Este lote</h2>
            {items.length === 0 ? (
              <p className="ticket__vacio">Toca un artículo para sumarlo.</p>
            ) : (
              <div className="ticket__lineas">
                {items.map(([id, n]) => {
                  const a = porId.get(id)!;
                  return (
                    <div key={id} className="linea">
                      <span className="linea__nombre">{a.nombre}</span>
                      <Contador chico valor={n} min={0} max={10000} onCambio={(v) => poner(id, v)} etiqueta={a.nombre} />
                      <span className="linea__precio num">Stock actual {a.stock} → {a.stock + n}</span>
                    </div>
                  );
                })}
              </div>
            )}
            <div className="ticket__total">
              <span className="muted">Total del lote</span>
              <strong>{unidades === 1 ? "1 pieza" : `${unidades} piezas`}</strong>
            </div>
            <Entrada etiqueta="Nota (opcional)" ayuda="Por ejemplo: PLA negro, tanda del sábado." value={nota} maxLength={300} onChange={(e) => setNota(e.target.value)} />
            <Boton variante="accent" bloque cargando={enviando} disabled={items.length === 0} onClick={registrar}>
              Sumar al inventario
            </Boton>
          </section>
        </div>
      )}

      {items.length > 0 && (
        <div className="barra-cobro">
          <strong>{unidades === 1 ? "1 pieza" : `${unidades} piezas`}</strong>
          <Boton variante="primary" onClick={() => document.getElementById("ticket")?.scrollIntoView({ block: "start" })}>
            Revisar y guardar
          </Boton>
        </div>
      )}

      <section className="seccion" aria-labelledby="t-hist">
        <h2 id="t-hist">Últimos lotes</h2>
        {(historial.datos ?? []).length === 0 ? (
          <div className="vacio"><p>Aún no registraste producción.</p></div>
        ) : (
          <div className="lista">
            {(historial.datos ?? []).map((p) => (
              <div key={p.id} className="fila fila--sin-foto">
                <span className="fila__titulo">
                  <span className="fila__nombre">{p.items.map((i) => `${i.cantidad} × ${i.nombre}`).join(", ")}</span>
                  <span className="fila__meta">{fechaHora(p.creado_en)}{p.nota ? ` · ${p.nota}` : ""}</span>
                </span>
                <span className="fila__fin num">+{p.items.reduce((s, i) => s + i.cantidad, 0)}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
