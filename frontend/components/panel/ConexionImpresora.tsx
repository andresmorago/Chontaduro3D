"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { Entrada } from "@/components/ui/Campo";
import { CampoClave } from "@/components/panel/CampoClave";
import { api } from "@/lib/api";
import { mensajeDe } from "@/lib/hooks";
import type { ConexionImpresora as Conexion } from "@/lib/types";

const pausa = (ms: number) => new Promise((ok) => setTimeout(ok, ms));

/** Texto y estilo del estado de la conexión con la impresora. */
export function estadoConexion(c: Conexion, esperando: boolean): { texto: string; clase: string } {
  if (!c.ip) return { texto: "Sin configurar", clase: "etiqueta--tenue" };
  if (c.ilegible) return { texto: "Hay que escribir el código otra vez", clase: "etiqueta--aviso" };
  if (!c.servicio_activo) return { texto: "Servicio detenido", clase: "etiqueta--aviso" };
  if (c.conectada) return { texto: "Conectada", clase: "etiqueta--ok" };
  if (c.pendiente || (esperando && !c.error)) return { texto: "Conectando…", clase: "etiqueta--tenue" };
  if (c.error === "credenciales") return { texto: "Código de acceso rechazado", clase: "etiqueta--aviso" };
  if (c.error === "red") return { texto: "No se alcanza la impresora", clase: "etiqueta--aviso" };
  return { texto: "Sin conexión", clase: "etiqueta--aviso" };
}

const EXPLICACION: Record<string, string> = {
  credenciales: "La impresora respondió pero no aceptó el código de acceso. Cópialo de nuevo de su pantalla (Ajustes → WLAN).",
  red: "No se llega a esa IP. Revisa que la impresora esté encendida, que la IP sea la correcta y que la VPN o la red local lleguen hasta ella.",
};

interface Props {
  conexion: Conexion;
  recargar: () => Promise<void>;
}

/** Formulario de IP, número de serie y código de acceso de la impresora. */
export function ConexionImpresora({ conexion, recargar }: Props) {
  const { mostrar } = useAvisos();
  const [ip, setIp] = useState(conexion.ip ?? "");
  const [serial, setSerial] = useState(conexion.serial ?? "");
  const [codigo, setCodigo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [esperando, setEsperando] = useState(false);
  const montado = useRef(true);
  useEffect(() => () => { montado.current = false; }, []);

  const estado = estadoConexion(conexion, esperando);
  const faltaCodigo = !conexion.codigo_guardado || conexion.ilegible;

  async function guardar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setGuardando(true);
    try {
      await api.impresora.conexion.guardar({ ip: ip.trim(), serial: serial.trim(), codigo_acceso: codigo.trim() || null });
      setCodigo("");
      setGuardando(false);
      setEsperando(true);
      // El servicio reconecta con lo nuevo en unos segundos: se espera su resultado.
      let c = await api.impresora.conexion.ver();
      for (let i = 0; i < 20 && montado.current && !((c.servicio_activo && !c.pendiente && (c.conectada || c.error)) || (!c.servicio_activo && i >= 2)); i++) {
        await pausa(1000);
        c = await api.impresora.conexion.ver();
      }
      await recargar();
      if (!montado.current) return;
      if (c.conectada) mostrar("Conectada con la impresora.");
      else if (!c.servicio_activo) mostrar("Guardado. El servicio de la impresora no está corriendo: en cuanto arranque se conecta.", { tipo: "error" });
      else mostrar((c.error && EXPLICACION[c.error]) || "Guardado, pero la impresora aún no responde.", { tipo: "error" });
    } catch (err) {
      setError(mensajeDe(err));
    } finally {
      if (montado.current) {
        setGuardando(false);
        setEsperando(false);
      }
    }
  }

  return (
    <form className="tarjeta bloque-clave" onSubmit={guardar}>
      <div className="impresora-estado__cab">
        <h3>Impresora Bambu Lab</h3>
        <span className={`etiqueta ${estado.clase}`} role="status">{estado.texto}</span>
      </div>
      <p className="muted">Se conecta por la red local (o la VPN). Los datos se guardan cifrados y el servicio los toma solo: no hay que tocar archivos ni reiniciar nada.</p>
      {error && <p className="alerta" role="alert">{error}</p>}
      {!esperando && !conexion.conectada && conexion.servicio_activo && conexion.error && !conexion.pendiente && (
        <p className="alerta" role="alert">{EXPLICACION[conexion.error]}</p>
      )}
      <Entrada etiqueta="IP de la impresora" value={ip} onChange={(e) => setIp(e.target.value)} inputMode="decimal" autoComplete="off" autoCapitalize="none" spellCheck={false} placeholder="192.168.1.50" ayuda="Está en la pantalla de la impresora: Ajustes → WLAN. Si la alcanzas por VPN, es la IP de la red remota." />
      <Entrada etiqueta="Número de serie" value={serial} onChange={(e) => setSerial(e.target.value)} autoComplete="off" autoCapitalize="characters" spellCheck={false} ayuda="Ajustes → Dispositivo, o la etiqueta bajo la impresora." />
      <CampoClave
        etiqueta="Código de acceso"
        valor={codigo}
        onCambio={setCodigo}
        autoComplete="off"
        ayuda={faltaCodigo ? "Ajustes → WLAN, en la pantalla de la impresora." : "Ya hay uno guardado: déjalo vacío para conservarlo."}
      />
      <Boton variante="accent" type="submit" cargando={guardando || esperando} disabled={!ip.trim() || !serial.trim() || (faltaCodigo && !codigo.trim())}>
        {esperando ? "Conectando…" : "Guardar y conectar"}
      </Boton>
    </form>
  );
}
