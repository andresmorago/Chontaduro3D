"use client";

import { useEffect, useState } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { Contador } from "@/components/ui/Contador";
import { Entrada } from "@/components/ui/Campo";
import { LoteEditarHoja } from "@/components/panel/LoteEditarHoja";
import { FilamentoTiempo } from "@/components/panel/FilamentoTiempo";
import { ParametrosHoja } from "@/components/panel/ParametrosHoja";
import { Selector } from "@/components/panel/Selector";
import { api } from "@/lib/api";
import { dinero, fechaCorta, hoyISO, restarDias } from "@/lib/format";
import { mensajeDe, useCargar } from "@/lib/hooks";
import { aExtra, gramos, kwhTexto, loteVacio, tiempoLargo } from "@/lib/produccion";
import type { Articulo, Produccion as Lote } from "@/lib/types";

export default function Produccion() {
  const { mostrar } = useAvisos();
  const articulos = useCargar(() => api.articulos.listar());
  const [limite, setLimite] = useState(30);
  const historial = useCargar(() => api.produccion.listar(limite));
  useEffect(() => {
    void historial.recargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limite]);
  const hoy = hoyISO();
  const parametros = useCargar(api.parametros.ver);
  const [verParametros, setVerParametros] = useState(false);
  const [lote, setLote] = useState(loteVacio());
  const [cantidades, setCantidades] = useState<Record<string, number>>({});
  const [nota, setNota] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [editando, setEditando] = useState<Lote | null>(null);

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
    const conv = aExtra(lote);
    if ("error" in conv) {
      mostrar(conv.error, { tipo: "error" });
      return;
    }
    setEnviando(true);
    try {
      await api.produccion.registrar(items.map(([articulo_id, cantidad]) => ({ articulo_id, cantidad })), nota.trim() || undefined, conv.extra);
      setCantidades({});
      setNota("");
      // Se conserva la fecha elegida: al cargar varios lotes del mismo día no hay que volver a ponerla.
      const fechaUsada = lote.fecha;
      const sumo = lote.sumar;
      setLote({ ...loteVacio(fechaUsada), sumar: sumo });
      const donde = sumo ? (unidades === 1 ? "entró" : "entraron") + " al inventario" : (unidades === 1 ? "quedó" : "quedaron") + " en el historial (sin sumar al stock)";
      mostrar(`Listo: ${unidades === 1 ? "1 pieza" : `${unidades} piezas`} ${donde}${fechaUsada !== hoy ? `, con fecha ${fechaCorta(fechaUsada)}` : ""}.`);
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
        <div className="pagina-cab__acciones">
          <Boton variante="secondary" pequeno onClick={() => setVerParametros(true)}>Parámetros de energía</Boton>
        </div>
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
            <div className="cuando">
              <label className="field">
                <span className="field__label">Fecha de producción</span>
                <input className="input num" type="date" value={lote.fecha} max={hoy} min={restarDias(hoy, 5 * 366)} onChange={(e) => setLote({ ...lote, fecha: e.target.value })} />
              </label>
              <label className="check">
                <input type="checkbox" checked={lote.sumar} onChange={(e) => setLote({ ...lote, sumar: e.target.checked })} />
                Sumar al inventario actual
              </label>
              {lote.fecha && lote.fecha < hoy && (
                <p className="field__hint">
                  Carga retrospectiva ({fechaCorta(lote.fecha)}). {lote.sumar ? "Estas piezas se SUMAN al stock de hoy; si ya se vendieron, desmarca la casilla y quedarán solo en el historial y las métricas." : "Solo quedará en el historial y las métricas: el stock de hoy no cambia."}
                </p>
              )}
            </div>
            <FilamentoTiempo valor={lote} onCambio={setLote} parametros={parametros.datos} onAbrirParametros={() => setVerParametros(true)} />
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
                  <span className="fila__meta num">
                    {fechaCorta(p.fecha)}
                    {p.gramos_total != null ? ` · ${gramos(p.gramos_total)}` : ""}
                    {p.minutos_impresion != null ? ` · ${tiempoLargo(p.minutos_impresion)}` : ""}
                    {p.kwh != null ? ` · ${kwhTexto(p.kwh)}` : ""}
                    {p.costo_energia != null ? ` · ${dinero(p.costo_energia)}` : ""}
                    {p.nota ? ` · ${p.nota}` : ""}
                    {!p.afecta_inventario ? " · solo historial" : ""}
                  </span>
                  {p.filamentos.length > 1 && (
                    <span className="fila__meta">{p.filamentos.map((f) => `${f.descripcion || "Filamento"} ${gramos(f.gramos)}`).join(" · ")}</span>
                  )}
                </span>
                <span className="fila__fin num">
                  +{p.items.reduce((s, i) => s + i.cantidad, 0)}
                  <Boton variante="secondary" pequeno onClick={() => setEditando(p)} aria-label={`Editar el lote del ${fechaCorta(p.fecha)}`}>Editar</Boton>
                </span>
              </div>
            ))}
          </div>
        )}
        {(historial.datos ?? []).length >= limite && limite < 100 && (
          <div><Boton variante="secondary" pequeno onClick={() => setLimite((n) => Math.min(100, n + 30))}>Ver más lotes</Boton></div>
        )}
      </section>
      <LoteEditarHoja
        lote={editando}
        articulos={lista}
        parametros={parametros.datos}
        onCerrar={() => setEditando(null)}
        onGuardado={() => void Promise.all([articulos.recargar(), historial.recargar()])}
        onAbrirParametros={() => setVerParametros(true)}
      />
      <ParametrosHoja abierta={verParametros} actuales={parametros.datos} onCerrar={() => setVerParametros(false)} onGuardado={() => void parametros.recargar()} />
    </>
  );
}
