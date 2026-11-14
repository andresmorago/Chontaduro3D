"use client";

import { useEffect, useRef, useState } from "react";
import { CENTRADO, geometria, type Encuadre } from "@/lib/foto";

interface Props {
  url: string | null;
  codigo: string;
  nombre: string;
  clase?: string;
  /** Qué parte de la foto se ve y con cuánto zoom (por defecto, centrada y completa). */
  enc?: Encuadre;
  /** Avisa de la proporción (ancho/alto) cuando la foto ya cargó (lo usa el editor de encuadre). */
  onRatio?: (ratio: number) => void;
}

/** La foto del artículo en un cuadro cuadrado, con su encuadre; si todavía no hay, se muestra su
 *  código (nunca una foto inventada). */
export function Foto({ url, codigo, nombre, clase, enc = CENTRADO, onRatio }: Props) {
  const [ratio, setRatio] = useState<number | null>(null);
  const img = useRef<HTMLImageElement>(null);
  const aviso = useRef(onRatio);
  aviso.current = onRatio;

  const medir = (i: HTMLImageElement) => {
    if (i.naturalWidth > 0 && i.naturalHeight > 0) {
      const r = i.naturalWidth / i.naturalHeight;
      setRatio(r);
      aviso.current?.(r);
    }
  };

  useEffect(() => {
    setRatio(null);
    const i = img.current;
    if (i?.complete) medir(i); // ya estaba en caché: el evento load pudo pasar antes de montar
  }, [url]);

  return (
    <div className={["foto", clase].filter(Boolean).join(" ")}>
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          ref={img}
          key={url}
          className={ratio ? "foto__enc" : "foto__enc foto__enc--medir"}
          style={ratio ? geometria(ratio, enc) : undefined}
          src={url}
          alt={nombre}
          width={600}
          height={600}
          loading="lazy"
          decoding="async"
          draggable={false}
          onLoad={(e) => medir(e.currentTarget)}
        />
      ) : (
        <span className="foto__marca" aria-hidden="true">
          {codigo}
        </span>
      )}
    </div>
  );
}
