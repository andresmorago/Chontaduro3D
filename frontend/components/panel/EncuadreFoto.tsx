"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Boton } from "@/components/ui/Boton";
import { Foto } from "@/components/ui/Foto";
import { CENTRADO, ZOOM_MAX, ZOOM_MIN, acotar, dimensiones, type Encuadre } from "@/lib/foto";

interface Props {
  url: string;
  valor: Encuadre;
  onCambio: (e: Encuadre) => void;
  /** Para los lectores de pantalla: de qué foto se trata. */
  etiqueta: string;
}

/** Elige qué parte de la foto se muestra: arrastrar para mover, rueda / pellizco / deslizador para el
 *  zoom, flechas del teclado. El cuadro es el mismo (cuadrado) que ve el cliente en el catálogo. */
export function EncuadreFoto({ url, valor, onCambio, etiqueta }: Props) {
  const caja = useRef<HTMLDivElement>(null);
  const [ratio, setRatio] = useState(1);
  const actual = useRef(valor);
  actual.current = valor;
  const alCambiar = useRef(onCambio);
  alCambiar.current = onCambio;
  const ratioRef = useRef(ratio);
  ratioRef.current = ratio;
  const punteros = useRef(new Map<number, { x: number; y: number }>());
  const distancia = useRef(0);

  const poner = (parcial: Partial<Encuadre>) => {
    const e = { ...actual.current, ...parcial };
    alCambiar.current({ x: acotar(e.x, 0, 100), y: acotar(e.y, 0, 100), zoom: acotar(e.zoom, ZOOM_MIN, ZOOM_MAX) });
  };

  /** Mover la foto `dx`,`dy` píxeles = cambiar el centro, según cuánto «sobra» de foto en cada eje. */
  function mover(dx: number, dy: number) {
    const lado = caja.current?.getBoundingClientRect().width ?? 0;
    if (!lado) return;
    const { ancho, alto } = dimensiones(ratioRef.current, actual.current.zoom);
    const e = actual.current;
    poner({
      x: ancho > 100.01 ? e.x + (dx * 10000) / (lado * (100 - ancho)) : e.x,
      y: alto > 100.01 ? e.y + (dy * 10000) / (lado * (100 - alto)) : e.y,
    });
  }

  // La rueda del ratón hace zoom (debe poder cancelar el scroll de la página: listener no pasivo).
  useEffect(() => {
    const el = caja.current;
    if (!el) return;
    const rueda = (ev: WheelEvent) => {
      ev.preventDefault();
      poner({ zoom: actual.current.zoom * Math.exp(-ev.deltaY * 0.002) });
    };
    el.addEventListener("wheel", rueda, { passive: false });
    return () => el.removeEventListener("wheel", rueda);
  }, []);

  function abajo(ev: PointerEvent<HTMLDivElement>) {
    ev.currentTarget.setPointerCapture(ev.pointerId);
    punteros.current.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (punteros.current.size === 2) {
      const [a, b] = [...punteros.current.values()];
      distancia.current = Math.hypot(a!.x - b!.x, a!.y - b!.y);
    }
  }
  function mueve(ev: PointerEvent<HTMLDivElement>) {
    const previo = punteros.current.get(ev.pointerId);
    if (!previo) return;
    punteros.current.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (punteros.current.size === 2) {
      // Pellizco: el zoom sigue la distancia entre los dos dedos.
      const [a, b] = [...punteros.current.values()];
      const d = Math.hypot(a!.x - b!.x, a!.y - b!.y);
      if (distancia.current > 0) poner({ zoom: actual.current.zoom * (d / distancia.current) });
      distancia.current = d;
    } else {
      mover(ev.clientX - previo.x, ev.clientY - previo.y);
    }
  }
  function arriba(ev: PointerEvent<HTMLDivElement>) {
    punteros.current.delete(ev.pointerId);
    distancia.current = 0;
  }
  function tecla(ev: KeyboardEvent<HTMLDivElement>) {
    const paso = 2;
    const e = actual.current;
    const mapa: Record<string, Partial<Encuadre>> = {
      ArrowLeft: { x: e.x - paso },
      ArrowRight: { x: e.x + paso },
      ArrowUp: { y: e.y - paso },
      ArrowDown: { y: e.y + paso },
      "+": { zoom: e.zoom + 0.1 },
      "=": { zoom: e.zoom + 0.1 },
      "-": { zoom: e.zoom - 0.1 },
    };
    const cambio = mapa[ev.key];
    if (cambio) {
      ev.preventDefault();
      poner(cambio);
    }
  }

  return (
    <div className="encuadre-editor">
      <div ref={caja} className="encuadre" tabIndex={0} role="group" aria-label={`Encuadre de ${etiqueta}. Flechas para mover, más y menos para el zoom.`} onPointerDown={abajo} onPointerMove={mueve} onPointerUp={arriba} onPointerCancel={arriba} onKeyDown={tecla}>
        <Foto url={url} codigo="" nombre="" enc={valor} onRatio={setRatio} />
        <span className="encuadre__guia" aria-hidden="true" />
      </div>
      <div className="encuadre-controles">
        <label className="encuadre-controles__zoom">
          <span className="field__label">Zoom</span>
          <input type="range" min={ZOOM_MIN} max={ZOOM_MAX} step={0.05} value={valor.zoom} onChange={(e) => poner({ zoom: Number(e.target.value) })} aria-label={`Zoom de ${etiqueta}`} />
        </label>
        <Boton variante="ghost" pequeno onClick={() => onCambio(CENTRADO)} disabled={valor.x === 50 && valor.y === 50 && valor.zoom === 1}>Restablecer</Boton>
      </div>
      <p className="field__hint">Arrastra para elegir qué parte se ve. Rueda, pellizco o el deslizador para acercar. Así lo verá el cliente.</p>
    </div>
  );
}
