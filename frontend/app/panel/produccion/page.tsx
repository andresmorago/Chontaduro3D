"use client";

import { useEffect, useState } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { Contador } from "@/components/ui/Contador";
import { Entrada } from "@/components/ui/Campo";
import { LoteEditarHoja } from "@/components/panel/LoteEditarHoja";
import { FilamentoTiempo } from "@/components/panel/FilamentoTiempo";
import { TrabajosImpresora } from "@/components/panel/TrabajosImpresora";
import { ParametrosHoja } from "@/components/panel/ParametrosHoja";
import { Selector } from "@/components/panel/Selector";
import { api } from "@/lib/api";
import { clave, hexColor, nombreColor, partirClave, stockDe } from "@/lib/lineas";
import { dinero, fechaCorta, hoyISO, restarDias } from "@/lib/format";
import { mensajeDe, useCargar } from "@/lib/hooks";
import { aExtra, gramos, kwhTexto, loteDesdeTrabajo, loteVacio, tiempoLargo } from "@/lib/produccion";
import type { Articulo, Produccion as Lote, TrabajoImpresora } from "@/lib/types";

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
  // Trabajo de la impresora que se está importando como este lote (y contador para recargar la bandeja).
  const [trabajo, setTrabajo] = useState<TrabajoImpresora | null>(null);
  const [version, setVersion] = useState(0);

  const lista = articulos.datos ?? [];
  const porId = new Map(lista.map((a) => [a.id, a]));
  // Cada línea es un (artículo, color): la clave las distingue (ver lib/lineas.ts).
  const items = Object.entries(cantidades).filter(([k, n]) => n > 0 && porId.has(partirClave(k).articuloId));
  const unidades = items.reduce((s, [, n]) => s + n, 0);

  const poner = (k: string, n: number) =>
    setCantidades((m) => {
      const { [k]: _q, ...resto } = m;
      void _q;
      return n <= 0 ? resto : { ...m, [k]: Math.min(10000, n) };
    });
  const cambiar = (a: Articulo, colorId: string | null, delta: number) => {
    const k = clave(a.id, colorId);
    poner(k, (cantidades[k] ?? 0) + delta);
  };

  function usarTrabajo(t: TrabajoImpresora) {
    setTrabajo(t);
    setLote(loteDesdeTrabajo(t));
    setNota(t.nombre);
    mostrar(`Cargué fecha, tiempo y filamento de «${t.nombre}». Elige qué piezas salieron y cuántas.`);
    document.getElementById("ticket")?.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  function soltarTrabajo() {
    setTrabajo(null);
    setLote(loteVacio(lote.fecha));
    setNota("");
  }

  async function registrar() {
    if (items.length === 0) return;
    const conv = aExtra(lote);
    if ("error" in conv) {
      mostrar(conv.error, { tipo: "error" });
      return;
    }
    setEnviando(true);
    try {
      await api.produccion.registrar(items.map(([k, cantidad]) => { const { articuloId, colorId } = partirClave(k); return { articulo_id: articuloId, ...(colorId ? { color_id: colorId } : {}), cantidad }; }), nota.trim() || undefined, trabajo ? { ...conv.extra, trabajo_id: trabajo.id } : conv.extra);
      setCantidades({});
      setNota("");
      setTrabajo(null);
      setVersion((n) => n + 1);
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
    <div className="pagina--ancha">
      <div className="pagina-cab pagina-cab--fila">
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
        <div className="venta-grid venta-grid--lote">
          <Selector articulos={lista} cantidades={Object.fromEntries(items)} onCambiar={cambiar} />
          <section className="ticket ticket--lote" id="ticket" aria-labelledby="t-lote">
            <h2 id="t-lote" className="ticket__titulo" style={{ fontSize: "var(--text-title)" }}>Este lote</h2>
            <div className="ticket__cuerpo">
              {items.length === 0 ? (
                <p className="ticket__vacio">Toca un artículo para sumarlo.</p>
              ) : (
                <div className="ticket__lineas">
                  {items.map(([k, n]) => {
                    const { articuloId, colorId } = partirClave(k);
                    const a = porId.get(articuloId)!;
                    const color = nombreColor(a, colorId);
                    const hay = stockDe(a, colorId);
                    return (
                      <div key={k} className="linea">
                        <span className="linea__nombre">
                          {a.nombre}
                          {color && (
                            <span className="linea__color">
                              <span className="muestra-mini" style={hexColor(a, colorId) ? { background: hexColor(a, colorId)! } : undefined} aria-hidden="true" />
                              {color}
                            </span>
                          )}
                        </span>
                        <Contador editable valor={n} min={0} max={10000} onCambio={(v) => poner(k, v)} etiqueta={`${a.nombre}${color ? `, ${color}` : ""}`} />
                        <span className="linea__precio num">Stock actual {hay} → {hay + n}</span>
                      </div>
                    );
                  })}
                </div>
              )}
              {trabajo && (
                <div className="vinculo-trabajo">
                  <span>Datos del trabajo <strong>«{trabajo.nombre}»</strong> de la impresora.</span>
                  <Boton variante="ghost" pequeno onClick={soltarTrabajo}>Quitar</Boton>
                </div>
              )}
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
            </div>
            <div className="ticket__pie">
              <div className="ticket__total">
                <span className="muted">Total del lote</span>
                <strong>{unidades === 1 ? "1 pieza" : `${unidades} piezas`}</strong>
              </div>
              <Boton variante="accent" bloque cargando={enviando} disabled={items.length === 0} onClick={registrar}>
                Sumar al inventario
              </Boton>
            </div>
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

      <TrabajosImpresora usandoId={trabajo?.id ?? null} onUsar={usarTrabajo} refrescar={version} />

      <section className="seccion seccion--lotes" aria-labelledby="t-hist">
        <h2 id="t-hist">Últimos lotes</h2>
        {(historial.datos ?? []).length === 0 ? (
          <div className="vacio"><p>Aún no registraste producción.</p></div>
        ) : (
          <div className="lista lista--dos">
            {(historial.datos ?? []).map((p) => (
              <div key={p.id} className="fila fila--sin-foto">
                <span className="fila__titulo">
                  <span className="fila__nombre">{p.items.map((i) => `${i.cantidad} × ${i.nombre}${i.color ? ` (${i.color})` : ""}`).join(", ")}</span>
                  <span className="fila__meta num">
                    {fechaCorta(p.fecha)}
                    {p.gramos_total != null ? ` · ${gramos(p.gramos_total)}` : ""}
                    {p.minutos_impresion != null ? ` · ${tiempoLargo(p.minutos_impresion)}` : ""}
                    {p.kwh != null ? ` · ${kwhTexto(p.kwh)}` : ""}
                    {p.costo_energia != null ? ` · ${dinero(p.costo_energia)}` : ""}
                    {p.nota ? ` · ${p.nota}` : ""}
                    {!p.afecta_inventario ? " · solo historial" : ""}
                    {p.desde_impresora ? " · de la impresora" : ""}
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
    </div>
  );
}
