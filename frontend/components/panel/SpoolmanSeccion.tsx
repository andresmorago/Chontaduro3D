"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { api, ErrorApi } from "@/lib/api";
import { fechaCorta, hace } from "@/lib/format";
import { ETIQUETA_CONSUMO, colorParecido, distanciaColor, gramosTexto, muestra, normTipo } from "@/lib/impresora";
import { mensajeDe, useCargar } from "@/lib/hooks";
import { Actividad, AvisoAlcance, DetalleAlcance, EditarRollo, MenuMas, Repuestos, Restante } from "@/components/panel/RollosSpoolman";
import type { BobinaSpoolman, ConsumoFilamento, RanuraSpoolman } from "@/lib/types";

const textoBobina = (b: BobinaSpoolman) => `${b.nombre} · ${b.restante_g != null ? gramosTexto(b.restante_g) : "sin peso"} · n.º ${b.id}`;

function Opciones({ bobinas }: { bobinas: BobinaSpoolman[] }) {
  return (
    <>
      <option value="">Elige una bobina…</option>
      {bobinas.map((b) => (
        <option key={b.id} value={b.id}>
          {textoBobina(b)}
        </option>
      ))}
    </>
  );
}

function Muestra({ color }: { color: string | null }) {
  return <span className="bandeja__color" style={{ background: muestra(color) }} aria-hidden="true" />;
}

/** Qué bobina de Spoolman hay en cada ranura del AMS. Las Bambu con chip se reconocen solas una vez vinculadas
 *  (el chip queda guardado en Spoolman); las demás se eligen a mano y se vuelven a confirmar si la ranura cambia. */
function Ranuras({ bobinas, recargarBobinas, autoregistro, respaldo, impresora }: { bobinas: BobinaSpoolman[]; recargarBobinas: () => Promise<void>; autoregistro: boolean; respaldo?: ReactNode; impresora?: EstadoParaLeer }) {
  const { mostrar } = useAvisos();
  const lista = useCargar(api.spoolman.ranuras);
  const alcance = useCargar(api.spoolman.alcance);
  const [editando, setEditando] = useState<string | null>(null);
  const [elegida, setElegida] = useState("");
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [creando, setCreando] = useState<string | null>(null);
  const [ajustando, setAjustando] = useState<string | null>(null);
  const [lectura, setLectura] = useState<Lectura | null>(null);
  const [form, setForm] = useState({ peso: "1000", restante: "", precio: "" });
  const [conflicto, setConflicto] = useState<{ ranura: string; spoolId: number; mensaje: string } | null>(null);

  useEffect(() => {
    const id = setInterval(() => {
      if (!document.hidden && editando === null) void lista.recargar();
      if (!document.hidden) void alcance.recargar();
    }, 5000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editando]);

  async function vincular(r: RanuraSpoolman, spoolId: number | null, mover = false) {
    setOcupado(r.ranura);
    try {
      await api.spoolman.vincular(r.ranura, spoolId, mover);
      mostrar(spoolId == null ? `${r.nombre}: bobina quitada.` : `${r.nombre}: bobina asociada.`);
      setEditando(null);
      setElegida("");
      setConflicto(null);
      await Promise.all([lista.recargar(), recargarBobinas()]);
    } catch (e) {
      if (e instanceof ErrorApi && e.status === 409 && spoolId != null) setConflicto({ ranura: r.ranura, spoolId, mensaje: e.message });
      else mostrar(mensajeDe(e), { tipo: "error" });
    } finally {
      setOcupado(null);
    }
  }

  /** Pide al AMS que vuelva a leer el chip de esa ranura (lo mismo que el botón «actualizar» de Bambu Studio). */
  async function releer(r: RanuraSpoolman) {
    setOcupado(r.ranura);
    setLectura({ ranura: r.ranura, fase: "leyendo", tag: null });
    try {
      let orden = await api.impresora.ordenar("leer_rfid", r.ranura);
      for (let i = 0; i < 10 && orden.estado === "pendiente"; i++) {
        await new Promise((ok) => setTimeout(ok, 700));
        orden = await api.impresora.orden(orden.id);
      }
      if (orden.estado !== "enviado") {
        setLectura(null);
        mostrar(orden.detalle ?? "La impresora no recibió la orden.", { tipo: "error" });
        return;
      }
      // El AMS lee y la impresora informa sola: se consulta cada pocos segundos hasta ver un cambio (o ~12 s).
      const antes = r.tag;
      let tag = antes;
      for (let i = 0; i < 5; i++) {
        await new Promise((ok) => setTimeout(ok, 2500));
        const filas = await api.spoolman.ranuras();
        tag = filas.find((f) => f.ranura === r.ranura)?.tag ?? null;
        if (tag !== antes) break;
      }
      setLectura({ ranura: r.ranura, fase: "listo", tag });
      await Promise.all([lista.recargar(), recargarBobinas()]);
    } catch (e) {
      setLectura(null);
      mostrar(mensajeDe(e), { tipo: "error" });
    } finally {
      setOcupado(null);
    }
  }

  async function crear(r: RanuraSpoolman) {
    const num = (t: string) => (t.trim() === "" ? undefined : Number(t.replace(",", ".")));
    const peso = num(form.peso), restante = num(form.restante), precio = num(form.precio);
    if ([peso, restante, precio].some((n) => n !== undefined && (!Number.isFinite(n) || n < 0)) || peso === 0) {
      mostrar("Revisa los números: pesos y precio deben ser positivos.", { tipo: "error" });
      return;
    }
    setOcupado(r.ranura);
    try {
      await api.spoolman.crearDesdeRanura(r.ranura, { peso_g: peso, restante_g: restante, precio });
      mostrar(`${r.nombre}: bobina creada en Spoolman y asociada.`);
      setCreando(null);
      await Promise.all([lista.recargar(), recargarBobinas()]);
    } catch (e) {
      mostrar(mensajeDe(e), { tipo: "error" });
    } finally {
      setOcupado(null);
    }
  }

  const filas = lista.datos ?? [];
  const sinLeer = motivoSinLeer(impresora);
  const unidas = filas.filter((r) => r.vinculo.bobina && r.vinculo.estado === "ok").length;
  return (
    <div className="spool-bloque">
      <h3 className="spool-sub">
        En la impresora ahora
        {filas.length > 0 && (
          <span className={`etiqueta ${unidas === filas.length ? "etiqueta--ok" : "etiqueta--aviso"}`}>
            {unidas} de {filas.length} unidas a Spoolman
          </span>
        )}
      </h3>
      <AvisoAlcance a={alcance.datos} />
      <details className="spool-ayuda">
        <summary>¿Cómo funciona?</summary>
        <p>
          Lo que ves lo informa la impresora en vivo. Cada ranura se une a una bobina de Spoolman, que es la que lleva los gramos. Las bobinas Bambu con chip se unen solas; las demás las eliges una vez.
        </p>
        <p>
          Para cambiar un rollo, cárgalo en la impresora (o en Bambu Studio). La app lo ve sola: los rollos Bambu con chip se registran en Spoolman; los demás se unen solos
          si en Spoolman hay uno del mismo material y color, o te pregunta cuál es. Esta app no cambia el filamento del AMS: el firmware de la impresora solo acepta esas órdenes si van firmadas por Bambu.
        </p>
        <p>
          <strong>Releer chip</strong> (en «Más») pide al AMS que vuelva a leer la etiqueta de esa bobina, como el botón de actualizar de Bambu Studio, y muestra el código leído.
          Si tu impresora rechaza la orden por la verificación de firmware, el panel te lo dirá.
        </p>
      </details>
      {lista.error && <p className="alerta" role="alert">{lista.error}</p>}
      {lista.cargando ? (
        <p className="muted" role="status">Cargando…</p>
      ) : filas.length === 0 ? (
        respaldo ?? <p className="muted">No hay filamento a la vista en la impresora. Cuando esté conectada y con ranuras cargadas, aparecen aquí.</p>
      ) : (
        <ul className="spool-ranuras">
          {filas.map((r) => {
            const v = r.vinculo;
            const abierto = editando === r.ranura;
            const necesidades = (alcance.datos?.lineas ?? []).filter((l) => l.ranura === r.ranura);
            const noAlcanza = necesidades.some((l) => l.estado === "no_alcanza");
            const tiene = Boolean(v.bobina && v.estado !== "sin_vincular");
            // La impresora no sabe que cambiaste el rollo si no tiene chip: sigue informando el color anterior.
            // Se muestra el de la bobina elegida y se avisa de la diferencia.
            const d = tiene ? distanciaColor(v.bobina!.color, r.color) : null;
            const colorDistinto = d !== null && d > 60;
            // Rollo nuevo sin registrar (o que cambió): si en Spoolman ya hay uno del mismo material y color que no está en el AMS, se ofrece.
            const sugeridas = !tiene || v.estado === "desactualizado"
              ? bobinas
                  .filter((b) => b.id !== v.bobina?.id && !(b.ubicacion ?? "").startsWith("AMS · ") && b.material && normTipo(b.material) === normTipo(r.tipo) && colorParecido(b.color, r.color))
                  .slice(0, 2)
              : [];
            return (
              <li key={r.ranura} className={`spool-ranura${r.en_uso ? " spool-ranura--uso" : ""}${noAlcanza ? " spool-ranura--falta" : ""}`}>
                <Muestra color={tiene && v.bobina!.color ? v.bobina!.color : r.color} />
                <div className="spool-ranura__texto">
                  <strong className="spool-ranura__titulo">
                    {r.nombre} <span className="muted">· {r.marca ?? r.tipo ?? "Filamento"}</span>
                    {colorDistinto && (
                      <span className="pildora pildora--aviso" title="Este rollo no tiene chip y la impresora sigue informando el color anterior. Cámbialo en la pantalla de la impresora o en Bambu Studio para que coincida.">
                        <span className="muestra-mini" style={{ background: muestra(r.color) }} aria-hidden="true" />
                        la impresora lo ve así
                      </span>
                    )}
                    {r.en_uso && <span className="pildora pildora--ok">En uso</span>}
                  </strong>
                  {tiene && v.bobina ? (
                    <span className="spool-ranura__sub">
                      {v.bobina.nombre} <span className="muted">· n.º {v.bobina.id}</span>
                      <span className="pildora" title={v.tipo === "rfid" ? "Se reconoce sola por el chip RFID" : "La asociaste a mano a esta ranura"}>{v.tipo === "rfid" ? "chip" : "a mano"}</span>
                      {r.tag && <code className="chip-uid" title="Código (UID) del chip RFID">{r.tag}</code>}
                    </span>
                  ) : (
                    <span className="spool-ranura__sub muted">
                      {v.tipo === "rfid"
                        ? autoregistro
                          ? "Bobina Bambu nueva: se registra sola en unos segundos."
                          : "Bobina Bambu con chip: aún no está en Spoolman."
                        : "Sin bobina asociada."}
                      {r.tag && <code className="chip-uid" title="Código (UID) del chip RFID">{r.tag}</code>}
                    </span>
                  )}
                </div>
                {tiene && v.bobina && <div className="spool-ranura__consumo"><Restante b={v.bobina} /></div>}
                {!abierto && creando !== r.ranura && ajustando !== r.ranura && (
                  <div className="spool-ranura__acciones">
                    {v.estado === "desactualizado" && v.bobina && (
                      <Boton variante="accent" pequeno cargando={ocupado === r.ranura} onClick={() => void vincular(r, v.bobina!.id)}>Sí, la misma</Boton>
                    )}
                    {!tiene && (
                      <Boton variante="accent" pequeno onClick={() => { setCreando(r.ranura); setForm({ peso: "1000", restante: "", precio: "" }); setConflicto(null); }}>
                        Crear en Spoolman
                      </Boton>
                    )}
                    {tiene && <Boton variante="secondary" pequeno onClick={() => { setAjustando(r.ranura); setConflicto(null); }}>Ajustar</Boton>}
                    <MenuMas>
                      <Boton variante="ghost" pequeno onClick={() => { setEditando(r.ranura); setElegida(v.bobina ? String(v.bobina.id) : ""); setConflicto(null); }}>
                        {tiene ? "Cambiar bobina de Spoolman" : "Elegir una existente"}
                      </Boton>
                      {r.ranura !== "254" && (
                        <Boton variante="ghost" pequeno disabled={sinLeer !== null} title={sinLeer ?? "Pide al AMS que vuelva a leer el chip de esta bobina"} cargando={ocupado === r.ranura} onClick={() => void releer(r)}>
                          Releer chip
                        </Boton>
                      )}
                      {tiene && <Boton variante="ghost" pequeno title="Solo desvincula la bobina en la app y en Spoolman. No cambia nada en la impresora: el rollo se descarga a mano." cargando={ocupado === r.ranura} onClick={() => void vincular(r, null)}>Desvincular de Spoolman</Boton>}
                    </MenuMas>
                  </div>
                )}
                {(sugeridas.length > 0 || lectura?.ranura === r.ranura || v.estado === "desactualizado" || necesidades.length > 0 || conflicto?.ranura === r.ranura || creando === r.ranura || abierto || ajustando === r.ranura) && (
                  <div className="spool-ranura__extra">
                    {v.estado === "desactualizado" && v.bobina && (
                      <span className="aviso-linea" role="status">La ranura cambió de filamento. ¿Sigue siendo esta bobina?</span>
                    )}
                    {sugeridas.length > 0 && (
                      <span className="lectura-chip">
                        <span className="muted">{v.estado === "desactualizado" ? "¿Cambiaste el rollo?" : "¿Es un rollo que ya tienes en Spoolman?"}</span>
                        {sugeridas.map((b) => (
                          <Boton key={b.id} variante="secondary" pequeno cargando={ocupado === r.ranura} onClick={() => void vincular(r, b.id)}>
                            Sí, es «{b.nombre}»
                          </Boton>
                        ))}
                      </span>
                    )}
                    {lectura?.ranura === r.ranura && (
                      <span className="lectura-chip" role="status">
                        {lectura.fase === "leyendo" ? (
                          <span className="muted">Leyendo el chip de {r.nombre}… tarda unos segundos.</span>
                        ) : lectura.tag ? (
                          <>
                            <span>Chip leído:</span>
                            <code className="chip-uid chip-uid--grande">{lectura.tag}</code>
                            <Boton variante="secondary" pequeno onClick={() => void navigator.clipboard?.writeText(lectura.tag!).then(() => mostrar("Código copiado."))}>Copiar</Boton>
                          </>
                        ) : (
                          <span>La impresora no detectó ningún chip en esta ranura. Puede ser un rollo sin chip (no Bambu) o que esté mal asentado.</span>
                        )}
                        {lectura.fase === "listo" && <Boton variante="ghost" pequeno onClick={() => setLectura(null)}>Cerrar</Boton>}
                      </span>
                    )}
                    {necesidades.map((l, i) => <DetalleAlcance key={i} l={l} />)}
                    {ajustando === r.ranura && v.bobina && (
                      <EditarRollo b={v.bobina} alCerrar={() => setAjustando(null)} alTerminar={async () => { await Promise.all([lista.recargar(), recargarBobinas()]); }} />
                    )}
                    {conflicto?.ranura === r.ranura && (
                      <span className="aviso-linea" role="alert">
                        {conflicto.mensaje}{" "}
                        <Boton variante="secondary" pequeno cargando={ocupado === r.ranura} onClick={() => void vincular(r, conflicto.spoolId, true)}>
                          Mover el chip
                        </Boton>
                      </span>
                    )}
                    {creando === r.ranura && (
                      <span className="spool-edicion spool-crear">
                        <label className="spool-gramos">
                          <span>Peso del rollo nuevo</span>
                          <input className="input num" inputMode="decimal" value={form.peso} onChange={(e) => setForm({ ...form, peso: e.target.value })} />
                          <span aria-hidden="true">g</span>
                        </label>
                        <label className="spool-gramos">
                          <span>Cuánto queda</span>
                          <input className="input num" inputMode="decimal" placeholder="lleno" value={form.restante} onChange={(e) => setForm({ ...form, restante: e.target.value })} />
                          <span aria-hidden="true">g</span>
                        </label>
                        <label className="spool-gramos">
                          <span>Precio</span>
                          <input className="input num" inputMode="decimal" placeholder="opcional" value={form.precio} onChange={(e) => setForm({ ...form, precio: e.target.value })} />
                        </label>
                        <Boton variante="accent" pequeno cargando={ocupado === r.ranura} onClick={() => void crear(r)}>Crear y asociar</Boton>
                        <Boton variante="ghost" pequeno onClick={() => setCreando(null)}>Cancelar</Boton>
                        <span className="field__hint">Se crea con la marca, el material y el color que informa la impresora. El precio va en la moneda que tenga Spoolman.</span>
                      </span>
                    )}
                    {abierto && (
                      <span className="spool-edicion">
                        <select className="select" aria-label={`Bobina de ${r.nombre}`} value={elegida} onChange={(e) => setElegida(e.target.value)}>
                          <Opciones bobinas={bobinas} />
                        </select>
                        <Boton variante="accent" pequeno disabled={!elegida} cargando={ocupado === r.ranura} onClick={() => void vincular(r, Number(elegida))}>
                          Guardar
                        </Boton>
                        <Boton variante="ghost" pequeno onClick={() => { setEditando(null); setConflicto(null); }}>Cancelar</Boton>
                      </span>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function FilaPendiente({ c, bobinas, alResolver }: { c: ConsumoFilamento; bobinas: BobinaSpoolman[]; alResolver: () => Promise<void> }) {
  const { mostrar } = useAvisos();
  const [spool, setSpool] = useState(c.spool_id ? String(c.spool_id) : "");
  const [g, setG] = useState(String(c.gramos));
  const [ocupado, setOcupado] = useState<string | null>(null);

  async function decidir(accion: "asignar" | "omitir" | "reintentar" | "confirmar", texto: string) {
    const gramos = Number(g.replace(",", "."));
    if (accion === "asignar" && (!spool || !Number.isFinite(gramos) || gramos < 0)) {
      mostrar("Elige la bobina e indica cuántos gramos descontar.", { tipo: "error" });
      return;
    }
    setOcupado(accion);
    try {
      await api.spoolman.decidir(c.id, accion === "asignar" ? { accion, spool_id: Number(spool), gramos } : { accion });
      mostrar(texto);
      await alResolver();
    } catch (e) {
      mostrar(mensajeDe(e), { tipo: "error" });
    } finally {
      setOcupado(null);
    }
  }

  return (
    <li className="spool-pendiente">
      <div className="spool-pendiente__cab">
        <Muestra color={c.color} />
        <div>
          <strong>{c.trabajo ?? "Trabajo"}</strong>
          <span className="muted num">
            {c.fecha ? ` · ${fechaCorta(c.fecha.slice(0, 10))}` : ""} · {c.tipo ?? "Filamento"} · {gramosTexto(c.gramos_plan)} en el archivo
          </span>
          <span className="etiqueta etiqueta--aviso">{ETIQUETA_CONSUMO[c.estado]}</span>
        </div>
      </div>
      {c.detalle && <p className="muted spool-pendiente__detalle">{c.detalle}</p>}
      {c.estado === "revisar" ? (
        <div className="spool-edicion">
          <Boton variante="accent" pequeno cargando={ocupado === "confirmar"} onClick={() => void decidir("confirmar", "Marcado como descontado.")}>Ya se descontó</Boton>
          <Boton variante="secondary" pequeno cargando={ocupado === "reintentar"} onClick={() => void decidir("reintentar", "Se descontará de nuevo en unos segundos.")}>Descontar otra vez</Boton>
          <Boton variante="ghost" pequeno cargando={ocupado === "omitir"} onClick={() => void decidir("omitir", "Omitido.")}>Omitir</Boton>
        </div>
      ) : (
        <div className="spool-edicion">
          <select className="select" aria-label="Bobina de la que salió el filamento" value={spool} onChange={(e) => setSpool(e.target.value)}>
            <Opciones bobinas={bobinas} />
          </select>
          <label className="spool-gramos">
            <span className="visually-hidden">Gramos a descontar</span>
            <input className="input num" inputMode="decimal" value={g} onChange={(e) => setG(e.target.value)} aria-label="Gramos a descontar" />
            <span aria-hidden="true">g</span>
          </label>
          <Boton variante="accent" pequeno cargando={ocupado === "asignar"} onClick={() => void decidir("asignar", "Se descontará de Spoolman en unos segundos.")}>Descontar</Boton>
          <Boton variante="ghost" pequeno cargando={ocupado === "omitir"} onClick={() => void decidir("omitir", "Omitido: no se descuenta.")}>Omitir</Boton>
        </div>
      )}
    </li>
  );
}

function Historial({ bobinas }: { bobinas: BobinaSpoolman[] }) {
  const [abierto, setAbierto] = useState(false);
  const lista = useCargar(() => (abierto ? api.spoolman.consumos(false) : Promise.resolve([] as ConsumoFilamento[])));
  useEffect(() => {
    if (abierto) void lista.recargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [abierto]);
  const nombre = (id: number | null) => (id == null ? "—" : (bobinas.find((b) => b.id === id)?.nombre ?? `n.º ${id}`));
  return (
    <details className="spool-historial" onToggle={(e) => setAbierto(e.currentTarget.open)}>
      <summary>Últimos descuentos</summary>
      {abierto && lista.cargando ? (
        <p className="muted" role="status">Cargando…</p>
      ) : (
        <ul className="spool-historial__lista">
          {(lista.datos ?? []).length === 0 && <li className="muted">Todavía no hay descuentos.</li>}
          {(lista.datos ?? []).map((c) => (
            <li key={c.id}>
              <Muestra color={c.color} />
              <span>
                <strong>{c.trabajo}</strong>{" "}
                <span className="muted num">
                  {gramosTexto(c.gramos)} · {nombre(c.spool_id)} · {c.estado === "descontado" && c.descontado_en ? `descontado ${hace(c.descontado_en)}` : ETIQUETA_CONSUMO[c.estado]}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

/** Spoolman en Administración → Impresora: estado, bobinas por ranura y descuentos que esperan una decisión. */
/** Lo que la sección necesita saber de la impresora para ofrecer «Releer chip». */
export interface EstadoParaLeer {
  estado: string;
  conectada: boolean;
}

/** Por qué no se puede releer un chip ahora (null = se puede). Como en Bambu Studio, el rollo que está en uso NO hay que descargarlo. */
function motivoSinLeer(i: EstadoParaLeer | undefined): string | null {
  if (!i || !i.conectada) return "La impresora no está conectada.";
  if (["preparando", "imprimiendo", "pausada"].includes(i.estado)) return "La impresora está imprimiendo: espera a que termine.";
  return null;
}

/** Resultado de «Releer chip» en una ranura: leyendo… y luego el código que informó la impresora. */
interface Lectura {
  ranura: string;
  fase: "leyendo" | "listo";
  tag: string | null;
}

export function SpoolmanSeccion({ respaldo, impresora }: { respaldo?: ReactNode; impresora?: EstadoParaLeer }) {
  const estado = useCargar(api.spoolman.estado);
  const e = estado.datos;

  useEffect(() => {
    const id = setInterval(() => {
      if (!document.hidden) void estado.recargar();
    }, 5000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section className="seccion seccion--ancha" id="spoolman" aria-labelledby="t-spoolman">
      <h2 id="t-spoolman">Filamento</h2>
      {estado.error && <p className="alerta" role="alert">{estado.error}</p>}
      {estado.cargando && <p className="muted" role="status">Cargando…</p>}
      {e && !e.configurado && (
        <>
          <p className="muted">Spoolman no está configurado en este servidor (falta <code>SPOOLMAN_URL</code>). Por ahora solo se ve lo que informa la impresora.</p>
          {respaldo}
        </>
      )}
      {e?.configurado && (
        <div className="tarjeta spool-tarjeta">
          <div className="spool-cab">
            <span className={`etiqueta ${e.conectado ? "etiqueta--ok" : "etiqueta--aviso"}`}>{e.conectado ? `En línea${e.version ? ` · v${e.version}` : ""}` : "Sin conexión"}</span>
            {!e.conectado && e.detalle && <span className="muted">{e.detalle}</span>}
            {e.url_web && (
              <a className="btn btn--secondary btn--small" href={e.url_web} target="_blank" rel="noopener noreferrer">
                Abrir Spoolman
              </a>
            )}
          </div>
          {e.url_web && <p className="field__hint">Spoolman solo se abre desde la red de casa (por la VPN).</p>}
          {e.conectado ? <Conectado porResolver={e.por_resolver} autoregistro={e.autoregistro} alCambiar={estado.recargar} respaldo={respaldo} impresora={impresora} /> : respaldo}
        </div>
      )}
    </section>
  );
}

function Conectado({ porResolver, autoregistro, alCambiar, respaldo, impresora }: { porResolver: number; autoregistro: boolean; alCambiar: () => Promise<void>; respaldo?: ReactNode; impresora?: EstadoParaLeer }) {
  const bobinas = useCargar(api.spoolman.bobinas);
  const pendientes = useCargar(() => api.spoolman.consumos(true));

  useEffect(() => {
    const id = setInterval(() => {
      if (!document.hidden) void pendientes.recargar();
    }, 5000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lista = bobinas.datos ?? [];
  const alResolver = async () => {
    await Promise.all([pendientes.recargar(), alCambiar()]);
  };
  const pend = pendientes.datos ?? [];
  return (
    <>
      {bobinas.error && <p className="alerta" role="alert">{bobinas.error}</p>}
      {!bobinas.cargando && lista.length === 0 && !bobinas.error && (
        <p className="alerta" role="status">Spoolman aún no tiene bobinas. Usa «Crear en Spoolman» en cada ranura (o créalas en Spoolman) y vuelve aquí.</p>
      )}
      <Ranuras bobinas={lista} autoregistro={autoregistro} respaldo={respaldo} impresora={impresora} recargarBobinas={async () => { await bobinas.recargar(); }} />
      <Actividad />
      <Repuestos alCambiar={async () => { await bobinas.recargar(); }} />
      <div className="spool-bloque">
        <h3 className="spool-sub">
          Descuentos por resolver {porResolver > 0 && <span className="etiqueta etiqueta--aviso">{porResolver}</span>}
        </h3>
        {pend.length === 0 ? (
          <p className="muted">Nada pendiente: cada trabajo terminado descuenta su filamento solo.</p>
        ) : (
          <ul className="spool-pendientes">
            {pend.map((c) => (
              <FilaPendiente key={`${c.id}-${c.estado}`} c={c} bobinas={lista} alResolver={alResolver} />
            ))}
          </ul>
        )}
      </div>
      <Historial bobinas={lista} />
    </>
  );
}
