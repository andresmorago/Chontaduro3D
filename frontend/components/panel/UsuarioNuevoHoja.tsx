"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useAvisos } from "@/components/ui/Avisos";
import { Boton } from "@/components/ui/Boton";
import { Entrada } from "@/components/ui/Campo";
import { Hoja } from "@/components/ui/Hoja";
import { CampoClave } from "@/components/panel/CampoClave";
import { api } from "@/lib/api";
import { motivoClaveDebil } from "@/lib/clave";
import { mensajeDe } from "@/lib/hooks";

interface Props {
  abierta: boolean;
  onCerrar: () => void;
  onCreado: () => void;
}

export function UsuarioNuevoHoja({ abierta, onCerrar, onCreado }: Props) {
  const { mostrar } = useAvisos();
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [clave, setClave] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    if (abierta) {
      setNombre("");
      setEmail("");
      setClave("");
      setError(null);
    }
  }, [abierta]);

  async function crear(e: FormEvent) {
    e.preventDefault();
    const debil = motivoClaveDebil(clave);
    if (debil) return setError(debil);
    setGuardando(true);
    setError(null);
    try {
      await api.usuarios.crear({ nombre: nombre.trim(), email: email.trim(), password: clave });
      mostrar(`Usuario creado: ${email.trim().toLowerCase()}. Pásale la contraseña temporal.`);
      onCreado();
      onCerrar();
    } catch (err) {
      setError(mensajeDe(err));
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Hoja
      abierta={abierta}
      onCerrar={onCerrar}
      titulo="Nuevo usuario"
      descripcion="Podrá entrar al panel con su correo y esta contraseña."
      pie={
        <>
          <Boton variante="secondary" onClick={onCerrar}>Cancelar</Boton>
          <Boton variante="accent" type="submit" form="form-usuario-nuevo" cargando={guardando}>Crear usuario</Boton>
        </>
      }
    >
      <form id="form-usuario-nuevo" onSubmit={crear} style={{ display: "grid", gap: "var(--space-md)" }}>
        {error && <p className="alerta" role="alert">{error}</p>}
        <Entrada etiqueta="Nombre" value={nombre} maxLength={80} required autoComplete="off" onChange={(e) => setNombre(e.target.value)} />
        <Entrada etiqueta="Correo" type="email" value={email} required autoComplete="off" autoCapitalize="none" onChange={(e) => setEmail(e.target.value)} />
        <CampoClave etiqueta="Contraseña temporal" valor={clave} onCambio={setClave} generar ayuda="Mínimo 10 caracteres, no solo números. Pídele que la cambie al entrar (Administración → Mi cuenta)." />
      </form>
    </Hoja>
  );
}
