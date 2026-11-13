"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { AreaTexto, Entrada } from "@/components/ui/Campo";
import { Hoja } from "@/components/ui/Hoja";
import { api } from "@/lib/api";
import { dinero, fechaHora } from "@/lib/format";
import { mensajeDe } from "@/lib/hooks";
import type { Articulo, PrecioHistorial } from "@/lib/types";

interface Props {
  /** `null` = cerrada; `"nuevo"` = crear; un artículo = editar. */
  objetivo: Articulo | "nuevo" | null;
  onCerrar: () => void;
  onGuardado: () => void;
}

export function ArticuloHoja({ objetivo, onCerrar, onGuardado }: Props) {
  const { mostrar } = useAvisos();
  const editando = objetivo !== null && objetivo !== "nuevo" ? objetivo : null;

  const [nombre, setNombre] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [precio, setPrecio] = useState("");
  const [minimo, setMinimo] = useState("0");
  const [publicado, setPublicado] = useState(true);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [vista, setVista] = useState<string | null>(null);
  const [historial, setHistorial] = useState<PrecioHistorial[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const entradaArchivo = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (objetivo === null) return;
    setError(null);
    setArchivo(null);
    if (objetivo === "nuevo") {
      setNombre("");
      setDescripcion("");
      setPrecio("");
      setMinimo("0");
      setPublicado(true);
      setVista(null);
      setHistorial([]);
    } else {
      setNombre(objetivo.nombre);
      setDescripcion(objetivo.descripcion);
      setPrecio(String(objetivo.precio_venta));
      setMinimo(String(objetivo.stock_minimo));
      setPublicado(objetivo.publicado);
      setVista(objetivo.imagen_url);
      api.articulos.precios(objetivo.id).then(setHistorial).catch(() => setHistorial([]));
    }
  }, [objetivo]);

  useEffect(() => {
    if (!archivo) return;
    const url = URL.createObjectURL(archivo);
    setVista(url);
    return () => URL.revokeObjectURL(url);
  }, [archivo]);

  async function guardar(e: FormEvent) {
    e.preventDefault();
    const p = Number(precio);
    const m = Number(minimo);
    if (!nombre.trim()) return setError("Ponle un nombre al artículo.");
    if (precio === "" || !Number.isFinite(p) || p < 0) return setError("Escribe un precio válido (0 o más).");
    if (!Number.isInteger(m) || m < 0) return setError("El stock mínimo debe ser un número entero, 0 o más.");

    setGuardando(true);
    setError(null);
    try {
      const datos = { nombre: nombre.trim(), descripcion: descripcion.trim(), precio_venta: p, stock_minimo: m, publicado };
      const guardado = editando ? await api.articulos.actualizar(editando.id, datos) : await api.articulos.crear(datos);
      let avisoFoto: string | null = null;
      if (archivo) {
        try {
          await api.articulos.subirImagen(guardado.id, archivo);
        } catch (errFoto) {
          // El artículo ya quedó guardado: no se deja la hoja abierta (un segundo «Guardar» lo duplicaría).
          avisoFoto = mensajeDe(errFoto);
        }
      }
      mostrar(editando ? "Cambios guardados." : `Artículo creado: ${guardado.codigo}.`);
      if (avisoFoto) mostrar(`La foto no se pudo subir: ${avisoFoto} Ábrelo de nuevo para reintentar.`, { tipo: "error" });
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
      return;
    }
    try {
      await api.articulos.quitarImagen(editando.id);
      setArchivo(null);
      setVista(null);
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
          <Boton variante="accent" type="submit" form="form-articulo" cargando={guardando}>Guardar</Boton>
        </>
      }
    >
      <form id="form-articulo" onSubmit={guardar} style={{ display: "grid", gap: "var(--space-md)" }}>
        {error && <p className="alerta" role="alert">{error}</p>}

        <div className="subida">
          <span className="field__label">Foto</span>
          {vista ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img className="subida__vista" src={vista} alt="Vista previa de la foto" width={220} height={220} />
          ) : (
            <p className="muted">Sin foto todavía: el catálogo mostrará el código del artículo.</p>
          )}
          <div style={{ display: "flex", gap: "var(--space-sm)", flexWrap: "wrap" }}>
            <Boton variante="secondary" pequeno onClick={() => entradaArchivo.current?.click()}>{vista ? "Cambiar foto" : "Subir foto"}</Boton>
            {vista && <Boton variante="ghost" pequeno onClick={quitarImagen}>Quitar</Boton>}
          </div>
          <input ref={entradaArchivo} className="visually-hidden" type="file" accept="image/jpeg,image/png,image/webp" tabIndex={-1} onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} aria-label="Elegir foto" />
          <p className="field__hint">JPG, PNG o WEBP, hasta 5 MB. Se ajusta sola.</p>
        </div>

        <Entrada etiqueta="Nombre" value={nombre} maxLength={120} required onChange={(e) => setNombre(e.target.value)} autoComplete="off" />
        <AreaTexto etiqueta="Descripción" ayuda="Qué es, tamaño, material. Lo verán los clientes." value={descripcion} maxLength={2000} onChange={(e) => setDescripcion(e.target.value)} />
        <div className="dos-col">
          <Entrada etiqueta="Precio de venta (COP)" type="number" inputMode="numeric" min={0} step={100} required value={precio} onChange={(e) => setPrecio(e.target.value)} ayuda={cambioPrecio ? "El cambio no afecta ventas ya registradas." : undefined} />
          <Entrada etiqueta="Avisar si quedan" type="number" inputMode="numeric" min={0} step={1} value={minimo} onChange={(e) => setMinimo(e.target.value)} ayuda="Piezas o menos. 0 = sin aviso." />
        </div>
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
