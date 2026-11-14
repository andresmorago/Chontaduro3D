"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { AreaTexto, Entrada } from "@/components/ui/Campo";
import { Foto } from "@/components/ui/Foto";
import { Hoja } from "@/components/ui/Hoja";
import { Icono } from "@/components/ui/Icono";
import { EncuadreFoto } from "@/components/panel/EncuadreFoto";
import { api } from "@/lib/api";
import { CENTRADO, aCampos, encuadreDe, esHeic, prepararFoto, type Encuadre } from "@/lib/foto";
import { dinero, fechaHora } from "@/lib/format";
import { mensajeDe } from "@/lib/hooks";
import type { Articulo, ArticuloEntrada, PrecioHistorial } from "@/lib/types";

interface Props {
  /** `null` = cerrada; `"nuevo"` = crear; un artículo = editar. */
  objetivo: Articulo | "nuevo" | null;
  onCerrar: () => void;
  onGuardado: () => void;
}

/** Un color en el formulario, con su foto opcional (la elegida ahora o la que ya tenía). */
interface FilaColor {
  id?: string;
  nombre: string;
  hex: string;
  imagen_url: string | null;
  enc: Encuadre;
  archivo: File | null;
  vista: string | null;
  heic: boolean;
  quitar: boolean;
  abierto: boolean;
}

const ACEPTA = "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif";
const fotoDe = (c: FilaColor) => c.vista ?? (c.quitar ? null : c.imagen_url);

export function ArticuloHoja({ objetivo, onCerrar, onGuardado }: Props) {
  const { mostrar } = useAvisos();
  const editando = objetivo !== null && objetivo !== "nuevo" ? objetivo : null;

  const [nombre, setNombre] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [precio, setPrecio] = useState("");
  const [minimo, setMinimo] = useState("0");
  const [publicado, setPublicado] = useState(true);
  const [colores, setColores] = useState<FilaColor[]>([]);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [vista, setVista] = useState<string | null>(null);
  const [heic, setHeic] = useState(false);
  const [preparando, setPreparando] = useState(false);
  const [enc, setEnc] = useState<Encuadre>(CENTRADO);
  const [historial, setHistorial] = useState<PrecioHistorial[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const entradaArchivo = useRef<HTMLInputElement>(null);
  const entradaColor = useRef<HTMLInputElement>(null);
  const colorEnSubida = useRef(0);
  const urls = useRef<string[]>([]); // vistas locales (blob:) para liberarlas

  const soltarUrls = () => {
    urls.current.forEach((u) => URL.revokeObjectURL(u));
    urls.current = [];
  };
  const nuevaUrl = (f: File) => {
    const u = URL.createObjectURL(f);
    urls.current.push(u);
    return u;
  };

  useEffect(() => {
    if (objetivo === null) return;
    soltarUrls();
    setError(null);
    setArchivo(null);
    setHeic(false);
    if (objetivo === "nuevo") {
      setNombre("");
      setDescripcion("");
      setPrecio("");
      setMinimo("0");
      setPublicado(true);
      setColores([]);
      setVista(null);
      setEnc(CENTRADO);
      setHistorial([]);
    } else {
      setNombre(objetivo.nombre);
      setDescripcion(objetivo.descripcion);
      setPrecio(String(objetivo.precio_venta));
      setMinimo(String(objetivo.stock_minimo));
      setPublicado(objetivo.publicado);
      setColores(objetivo.colores.map((c) => ({ id: c.id, nombre: c.nombre, hex: c.hex, imagen_url: c.imagen_url, enc: encuadreDe(c), archivo: null, vista: null, heic: false, quitar: false, abierto: false })));
      setVista(objetivo.imagen_url);
      setEnc(encuadreDe(objetivo));
      api.articulos.precios(objetivo.id).then(setHistorial).catch(() => setHistorial([]));
    }
    return soltarUrls;
  }, [objetivo]);

  async function elegirFoto(original: File | null) {
    if (!original) return;
    setPreparando(true);
    const f = await prepararFoto(original); // se achica antes de subir: una foto de celular pesa varios MB
    setPreparando(false);
    setArchivo(f);
    setEnc(CENTRADO); // una foto nueva empieza centrada y completa
    // Un HEIC no se puede mostrar en el navegador de escritorio: el servidor lo convierte al guardar.
    setHeic(esHeic(f));
    setVista(esHeic(f) ? null : nuevaUrl(f));
  }

  const actColor = (i: number, parcial: Partial<FilaColor>) => setColores((cs) => cs.map((c, j) => (j === i ? { ...c, ...parcial } : c)));

  async function elegirFotoColor(original: File | null) {
    const i = colorEnSubida.current;
    if (!original) return;
    setPreparando(true);
    const f = await prepararFoto(original);
    setPreparando(false);
    actColor(i, { archivo: f, quitar: false, enc: CENTRADO, heic: esHeic(f), vista: esHeic(f) ? null : nuevaUrl(f), abierto: true });
  }

  async function guardar(e: FormEvent) {
    e.preventDefault();
    const p = Number(precio);
    const m = Number(minimo);
    if (!nombre.trim()) return setError("Ponle un nombre al artículo.");
    if (precio === "" || !Number.isFinite(p) || p < 0) return setError("Escribe un precio válido (0 o más).");
    if (!Number.isInteger(m) || m < 0) return setError("El stock mínimo debe ser un número entero, 0 o más.");
    const limpios = colores.map((c) => ({ ...c, nombre: c.nombre.trim().replace(/\s+/g, " ") }));
    if (limpios.some((c) => !c.nombre)) return setError("Cada color necesita un nombre (o quítalo).");
    const vistos = new Set<string>();
    for (const c of limpios) {
      const k = c.nombre.toLocaleLowerCase("es");
      if (vistos.has(k)) return setError(`El color «${c.nombre}» está repetido.`);
      vistos.add(k);
    }

    setGuardando(true);
    setError(null);
    try {
      const datos: ArticuloEntrada = {
        nombre: nombre.trim(), descripcion: descripcion.trim(), precio_venta: p, stock_minimo: m, publicado,
        ...aCampos(enc),
        colores: limpios.map((c) => ({ ...(c.id ? { id: c.id } : {}), nombre: c.nombre, hex: c.hex, ...aCampos(c.enc) })),
      };
      const guardado = editando ? await api.articulos.actualizar(editando.id, datos) : await api.articulos.crear(datos);
      // Las fotos van aparte: el artículo ya quedó guardado aunque alguna falle (no se deja la hoja
      // abierta: un segundo «Guardar» lo duplicaría).
      const fallos: string[] = [];
      if (archivo) {
        try {
          await api.articulos.subirImagen(guardado.id, archivo);
        } catch (errFoto) {
          fallos.push(`la foto principal (${mensajeDe(errFoto)})`);
        }
      }
      for (const [i, c] of limpios.entries()) {
        const destino = guardado.colores[i]; // vienen en el mismo orden en que se enviaron
        if (!destino) continue;
        try {
          if (c.archivo) await api.articulos.subirImagenColor(guardado.id, destino.id, c.archivo);
          else if (c.quitar && c.imagen_url) await api.articulos.quitarImagenColor(guardado.id, destino.id);
        } catch (errFoto) {
          fallos.push(`la del color ${c.nombre} (${mensajeDe(errFoto)})`);
        }
      }
      mostrar(editando ? "Cambios guardados." : `Artículo creado: ${guardado.codigo}.`);
      if (fallos.length) mostrar(`El artículo se guardó, pero NO se pudo subir ${fallos.join("; ")}. Ábrelo de nuevo para reintentar.`, { tipo: "error", ms: 15000 });
      onGuardado();
      onCerrar();
    } catch (err) {
      setError(mensajeDe(err));
    } finally {
      setGuardando(false);
    }
  }

  async function quitarImagen() {
    if (!editando) {
      setArchivo(null);
      setVista(null);
      setHeic(false);
      return;
    }
    try {
      await api.articulos.quitarImagen(editando.id);
      setArchivo(null);
      setVista(null);
      setHeic(false);
      onGuardado();
    } catch (err) {
      setError(mensajeDe(err));
    }
  }

  async function archivar(activo: boolean) {
    if (!editando) return;
    try {
      await api.articulos.actualizar(editando.id, { activo });
      mostrar(activo ? "Artículo restaurado." : "Artículo archivado. Ya no aparece en ventas ni en el catálogo.");
      onGuardado();
      onCerrar();
    } catch (err) {
      setError(mensajeDe(err));
    }
  }

  const cambioPrecio = editando && Number(precio) !== editando.precio_venta && precio !== "";

  return (
    <Hoja
      abierta={objetivo !== null}
      onCerrar={onCerrar}
      titulo={editando ? "Editar artículo" : "Nuevo artículo"}
      descripcion={editando ? `${editando.codigo} · stock ${editando.stock}` : "El código se asigna solo."}
      pie={
        <>
          <Boton variante="secondary" onClick={onCerrar}>Cancelar</Boton>
          <Boton variante="accent" type="submit" form="form-articulo" cargando={guardando || preparando} disabled={preparando}>{preparando ? "Preparando foto…" : "Guardar"}</Boton>
        </>
      }
    >
      <form id="form-articulo" onSubmit={guardar} style={{ display: "grid", gap: "var(--space-md)" }}>
        {error && <p className="alerta" role="alert">{error}</p>}

        <div className="subida">
          <span className="field__label">Foto</span>
          {vista ? (
            <EncuadreFoto url={vista} valor={enc} onCambio={setEnc} etiqueta={nombre.trim() || "este artículo"} />
          ) : heic ? (
            <p className="field__hint">Foto HEIC lista: se convierte al guardar. Para elegir el encuadre, guarda y vuelve a abrir el artículo.</p>
          ) : (
            <p className="muted">Sin foto todavía: el catálogo mostrará el código del artículo.</p>
          )}
          <div style={{ display: "flex", gap: "var(--space-sm)", flexWrap: "wrap" }}>
            <Boton variante="secondary" pequeno onClick={() => entradaArchivo.current?.click()}>{vista || heic ? "Cambiar foto" : "Subir foto"}</Boton>
            {(vista || heic) && <Boton variante="ghost" pequeno onClick={quitarImagen}>Quitar</Boton>}
          </div>
          <input ref={entradaArchivo} className="visually-hidden" type="file" accept={ACEPTA} tabIndex={-1} onChange={(e) => { void elegirFoto(e.target.files?.[0] ?? null); e.target.value = ""; }} aria-label="Elegir foto" />
          <p className="field__hint">JPG, PNG, WEBP o HEIC (iPhone). Se achica sola antes de subir.</p>
        </div>

        <Entrada etiqueta="Nombre" value={nombre} maxLength={120} required onChange={(e) => setNombre(e.target.value)} autoComplete="off" />
        <AreaTexto etiqueta="Descripción" ayuda="Qué es, tamaño, material. Lo verán los clientes." value={descripcion} maxLength={2000} onChange={(e) => setDescripcion(e.target.value)} />
        <div className="dos-col">
          <Entrada etiqueta="Precio de venta (COP)" type="number" inputMode="numeric" min={0} step={100} required value={precio} onChange={(e) => setPrecio(e.target.value)} ayuda={cambioPrecio ? "El cambio no afecta ventas ya registradas." : undefined} />
          <Entrada etiqueta="Avisar si quedan" type="number" inputMode="numeric" min={0} step={1} value={minimo} onChange={(e) => setMinimo(e.target.value)} ayuda="Piezas o menos. 0 = sin aviso." />
        </div>

        <fieldset className="colores-editor">
          <legend className="field__label">Colores disponibles (opcional)</legend>
          <p className="field__hint">Si agregas colores, el cliente elige uno al pedir. Cada color puede tener su propia foto (opcional); si no la tiene, se muestra la del artículo.</p>
          {colores.map((c, i) => {
            const foto = fotoDe(c);
            return (
              <div key={c.id ?? `nuevo-${i}`} className="color-item">
                <div className="color-fila">
                  <input className="color-fila__muestra" type="color" value={c.hex} aria-label={`Muestra del color ${i + 1}`} onChange={(e) => actColor(i, { hex: e.target.value })} />
                  <input className="input" maxLength={30} placeholder="Ej. Rojo" aria-label={`Nombre del color ${i + 1}`} value={c.nombre} onChange={(e) => actColor(i, { nombre: e.target.value })} />
                  <button type="button" className="color-foto-btn" aria-expanded={c.abierto} aria-label={`Foto del color ${c.nombre || i + 1}`} onClick={() => actColor(i, { abierto: !c.abierto })}>
                    {foto ? <Foto url={foto} codigo="" nombre="" enc={c.enc} clase="color-foto-btn__mini" /> : <Icono nombre="foto" tamano={20} />}
                  </button>
                  <Boton variante="ghost" pequeno aria-label={`Quitar el color ${c.nombre || i + 1}`} onClick={() => setColores(colores.filter((_, j) => j !== i))}>Quitar</Boton>
                </div>
                {c.abierto && (
                  <div className="color-foto">
                    {foto ? (
                      <EncuadreFoto url={foto} valor={c.enc} onCambio={(e) => actColor(i, { enc: e })} etiqueta={`el color ${c.nombre || i + 1}`} />
                    ) : c.heic ? (
                      <p className="field__hint">Foto HEIC lista: se convierte al guardar. Para elegir el encuadre, guarda y vuelve a abrir el artículo.</p>
                    ) : (
                      <p className="muted">Este color no tiene foto propia: se muestra la del artículo.</p>
                    )}
                    <div style={{ display: "flex", gap: "var(--space-sm)", flexWrap: "wrap" }}>
                      <Boton variante="secondary" pequeno onClick={() => { colorEnSubida.current = i; entradaColor.current?.click(); }}>{foto || c.heic ? "Cambiar foto" : "Subir foto de este color"}</Boton>
                      {(foto || c.heic) && <Boton variante="ghost" pequeno onClick={() => actColor(i, { archivo: null, vista: null, heic: false, quitar: true, enc: CENTRADO })}>Quitar foto</Boton>}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {colores.length < 20 && (
            <div>
              <Boton variante="secondary" pequeno onClick={() => setColores([...colores, { nombre: "", hex: "#9ca3af", imagen_url: null, enc: CENTRADO, archivo: null, vista: null, heic: false, quitar: false, abierto: false }])}>+ Agregar color</Boton>
            </div>
          )}
          <input ref={entradaColor} className="visually-hidden" type="file" accept={ACEPTA} tabIndex={-1} onChange={(e) => { void elegirFotoColor(e.target.files?.[0] ?? null); e.target.value = ""; }} aria-label="Elegir foto del color" />
        </fieldset>

        <label className="check">
          <input type="checkbox" checked={publicado} onChange={(e) => setPublicado(e.target.checked)} />
          Mostrar en el catálogo público
        </label>

        {editando && historial.length > 0 && (
          <section>
            <h3 style={{ fontSize: "var(--text-md)", marginBottom: "var(--space-xs)" }}>Precios anteriores</h3>
            <ul className="historial" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {historial.map((h, i) => (
                <li key={h.cambiado_en + i}>
                  <span className="muted">{fechaHora(h.cambiado_en)}</span>
                  <span>{dinero(h.precio)}{i === 0 ? " (actual)" : ""}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {editando && (
          <div style={{ borderTop: "var(--rule-hair) solid var(--color-rule)", paddingTop: "var(--space-md)" }}>
            {editando.activo ? (
              <Boton variante="danger" pequeno onClick={() => archivar(false)}>Archivar artículo</Boton>
            ) : (
              <Boton variante="secondary" pequeno onClick={() => archivar(true)}>Restaurar artículo</Boton>
            )}
            <p className="field__hint" style={{ marginTop: "var(--space-xs)" }}>Archivar no borra nada: el historial de ventas y movimientos se conserva.</p>
          </div>
        )}
      </form>
    </Hoja>
  );
}
