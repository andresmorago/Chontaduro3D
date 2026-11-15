"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { Entrada } from "@/components/ui/Campo";
import { CampoClave } from "@/components/panel/CampoClave";
import { api } from "@/lib/api";
import { hace } from "@/lib/format";
import { mensajeDe } from "@/lib/hooks";
import type { ConexionImpresora } from "@/lib/types";

const pausa = (ms: number) => new Promise((ok) => setTimeout(ok, ms));

type Paso = { tipo: "inicio" } | { tipo: "codigo" } | { tipo: "tfa"; llave: string } | { tipo: "token" };

interface Props {
  conexion: ConexionImpresora;
  recargar: () => Promise<void>;
}

/** Vincular la cuenta de Bambu Lab (historial de trabajos de Studio y Handy), sin terminal. */
export function ConexionNube({ conexion, recargar }: Props) {
  const { mostrar } = useAvisos();
  const nube = conexion.nube;
  const [paso, setPaso] = useState<Paso>({ tipo: "inicio" });
  const [correo, setCorreo] = useState("");
  const [clave, setClave] = useState("");
  const [codigo, setCodigo] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [confirmar, setConfirmar] = useState(false);
  const montado = useRef(true);
  useEffect(() => () => { montado.current = false; }, []);

  /** Espera a que el servicio atienda la sincronización pedida y dice cómo le fue. */
  async function esperarSincronizacion() {
    let c = await api.impresora.conexion.ver();
    for (let i = 0; i < 30 && montado.current && c.nube.pendiente; i++) {
      await pausa(1000);
      c = await api.impresora.conexion.ver();
    }
    await recargar();
    if (!montado.current) return;
    if (c.nube.pendiente) mostrar("El servicio de la impresora aún no responde; sincronizará en cuanto arranque.", { tipo: "error" });
    else if (c.nube.estado === "ok") mostrar("Historial sincronizado.");
    else if (c.nube.estado === "requiere_login") mostrar("Bambu no aceptó el acceso guardado: vincula la cuenta de nuevo.", { tipo: "error" });
    else mostrar(c.nube.detalle ?? "No se pudo consultar Bambu Cloud.", { tipo: "error" });
  }

  async function terminarVinculo(texto: string) {
    setClave("");
    setCodigo("");
    setToken("");
    setPaso({ tipo: "inicio" });
    await recargar();
    mostrar(texto);
    await esperarSincronizacion();
  }

  async function ejecutar(accion: () => Promise<void>) {
    setError(null);
    setOcupado(true);
    try {
      await accion();
    } catch (err) {
      setError(mensajeDe(err));
    } finally {
      if (montado.current) setOcupado(false);
    }
  }

  const entrar = (e: FormEvent) => {
    e.preventDefault();
    void ejecutar(async () => {
      const r = await api.impresora.conexion.nubeEntrar(correo.trim(), clave);
      setClave(""); // la contraseña no se queda en pantalla ni en memoria
      if (r.paso === "listo") await terminarVinculo("Cuenta de Bambu Lab vinculada.");
      else if (r.paso === "codigo") setPaso({ tipo: "codigo" });
      else setPaso({ tipo: "tfa", llave: r.tfa_key ?? "" });
    });
  };

  const verificar = (e: FormEvent) => {
    e.preventDefault();
    void ejecutar(async () => {
      await api.impresora.conexion.nubeVerificar(paso.tipo === "tfa" ? { codigo: codigo.trim(), tfa_key: paso.llave } : { codigo: codigo.trim(), correo: correo.trim() });
      await terminarVinculo("Cuenta de Bambu Lab vinculada.");
    });
  };

  const pegarToken = (e: FormEvent) => {
    e.preventDefault();
    void ejecutar(async () => {
      await api.impresora.conexion.nubeToken(token.trim());
      await terminarVinculo("Token guardado.");
    });
  };

  const sincronizar = () =>
    void ejecutar(async () => {
      await api.impresora.conexion.nubeSincronizar();
      await recargar();
      await esperarSincronizacion();
    });

  const desvincular = () =>
    void ejecutar(async () => {
      await api.impresora.conexion.nubeDesvincular();
      setConfirmar(false);
      await recargar();
      mostrar("Cuenta desvinculada. Los trabajos ya traídos se conservan.");
    });

  const problema = nube.estado === "requiere_login" || nube.estado === "error";

  return (
    <div className="tarjeta bloque-clave">
      <div className="impresora-estado__cab">
        <h3>Cuenta de Bambu Lab</h3>
        <span className={`etiqueta ${nube.vinculada ? (problema ? "etiqueta--aviso" : "etiqueta--ok") : "etiqueta--tenue"}`} role="status">
          {nube.vinculada ? (nube.estado === "requiere_login" ? "Hay que volver a vincular" : "Vinculada") : "Sin vincular"}
        </span>
      </div>
      <p className="muted">Trae a Producción los trabajos que ya hiciste con Bambu Studio o Handy (últimos días). La contraseña solo se usa para entrar: no se guarda, solo el acceso que Bambu entrega, cifrado.</p>
      {error && <p className="alerta" role="alert">{error}</p>}

      {nube.vinculada ? (
        <>
          <p>
            {nube.correo ? <>Cuenta <strong>{nube.correo}</strong>. </> : null}
            {nube.pendiente
              ? "Sincronizando…"
              : nube.estado === "ok" && nube.sincronizada_en
                ? `Última sincronización ${hace(nube.sincronizada_en)}; se repite cada 10 minutos.`
                : nube.estado === "error"
                  ? `No se pudo consultar (${nube.detalle ?? "error"}). Se reintenta solo.`
                  : nube.estado === "requiere_login"
                    ? (nube.detalle ?? "El acceso venció.")
                    : "Aún no se ha sincronizado."}
          </p>
          <div className="impresora-controles__fila">
            <Boton variante="accent" cargando={ocupado || nube.pendiente} onClick={sincronizar}>Sincronizar ahora</Boton>
            {confirmar ? (
              <>
                <Boton variante="danger" disabled={ocupado} onClick={desvincular}>Sí, desvincular</Boton>
                <Boton variante="secondary" onClick={() => setConfirmar(false)}>No</Boton>
              </>
            ) : (
              <Boton variante="secondary" onClick={() => setConfirmar(true)}>Desvincular</Boton>
            )}
          </div>
          {nube.estado === "requiere_login" && <p className="muted">Para renovar el acceso, desvincula y vuelve a vincular la cuenta.</p>}
        </>
      ) : paso.tipo === "inicio" ? (
        <form className="bloque-clave" style={{ padding: 0, border: 0, boxShadow: "none", background: "none" }} onSubmit={entrar}>
          <Entrada etiqueta="Correo de tu cuenta Bambu" type="email" value={correo} onChange={(e) => setCorreo(e.target.value)} autoComplete="off" autoCapitalize="none" spellCheck={false} />
          <CampoClave etiqueta="Contraseña" valor={clave} onCambio={setClave} autoComplete="off" />
          <Boton variante="accent" type="submit" cargando={ocupado} disabled={!correo.trim() || !clave}>Vincular cuenta</Boton>
          <Boton variante="ghost" pequeno onClick={() => { setError(null); setPaso({ tipo: "token" }); }}>No me deja entrar: pegar el token</Boton>
        </form>
      ) : paso.tipo === "token" ? (
        <form className="bloque-clave" style={{ padding: 0, border: 0, boxShadow: "none", background: "none" }} onSubmit={pegarToken}>
          <p className="muted">Entra a bambulab.com en el navegador, abre las herramientas (F12) → Aplicación → Cookies → bambulab.com y copia el valor de la cookie «token». No se renueva solo: cuando venza hay que repetirlo.</p>
          <CampoClave etiqueta="Token" valor={token} onCambio={setToken} autoComplete="off" />
          <div className="impresora-controles__fila">
            <Boton variante="accent" type="submit" cargando={ocupado} disabled={token.trim().length < 20}>Guardar token</Boton>
            <Boton variante="secondary" onClick={() => { setError(null); setPaso({ tipo: "inicio" }); }}>Volver</Boton>
          </div>
        </form>
      ) : (
        <form className="bloque-clave" style={{ padding: 0, border: 0, boxShadow: "none", background: "none" }} onSubmit={verificar}>
          <p>{paso.tipo === "codigo" ? <>Bambu te envió un código por correo a <strong>{correo}</strong>.</> : "Escribe el código de tu app de autenticación (2FA)."}</p>
          <Entrada etiqueta="Código de verificación" value={codigo} onChange={(e) => setCodigo(e.target.value)} inputMode="numeric" autoComplete="one-time-code" />
          <div className="impresora-controles__fila">
            <Boton variante="accent" type="submit" cargando={ocupado} disabled={codigo.trim().length < 4}>Confirmar</Boton>
            <Boton variante="secondary" onClick={() => { setError(null); setCodigo(""); setPaso({ tipo: "inicio" }); }}>Volver</Boton>
          </div>
        </form>
      )}
    </div>
  );
}
