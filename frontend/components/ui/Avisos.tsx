"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

interface Aviso {
  id: number;
  texto: string;
  tipo: "info" | "error";
  accion?: { etiqueta: string; alPulsar: () => void | Promise<void> };
}

interface Contexto {
  mostrar: (texto: string, o?: { tipo?: Aviso["tipo"]; accion?: Aviso["accion"]; ms?: number }) => void;
}

const Ctx = createContext<Contexto>({ mostrar: () => {} });
export const useAvisos = () => useContext(Ctx);

export function ProveedorAvisos({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const siguiente = useRef(1);

  const quitar = useCallback((id: number) => setAvisos((a) => a.filter((x) => x.id !== id)), []);

  const mostrar = useCallback<Contexto["mostrar"]>(
    (texto, o = {}) => {
      const id = siguiente.current++;
      setAvisos((a) => [...a.slice(-2), { id, texto, tipo: o.tipo ?? "info", accion: o.accion }]);
      // Los avisos con acción (Deshacer) duran más: hay que alcanzar a pulsarla.
      setTimeout(() => quitar(id), o.ms ?? (o.accion ? 9000 : o.tipo === "error" ? 7000 : 4000));
    },
    [quitar],
  );

  const valor = useMemo(() => ({ mostrar }), [mostrar]);

  return (
    <Ctx.Provider value={valor}>
      {children}
      <div className="avisos" role="status" aria-live="polite">
        {avisos.map((a) => (
          <div key={a.id} className={`aviso${a.tipo === "error" ? " aviso--error" : ""}`}>
            <span className="aviso__texto">{a.texto}</span>
            {a.accion && (
              <button
                type="button"
                className="aviso__accion"
                onClick={async () => {
                  quitar(a.id);
                  await a.accion?.alPulsar();
                }}
              >
                {a.accion.etiqueta}
              </button>
            )}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
