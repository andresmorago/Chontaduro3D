# Design — Mis impresiones

Sistema de diseño bloqueado de la app (catálogo público + panel). Todo cambio visual lee este archivo primero.
Redesign v2 (2026-11-13): de Terrazzo (claro, editorial) a **Squeeze** (verde profundo, tarjetas crema, color y energía) para que el catálogo sea más llamativo sin perder seriedad.

## Genre
playful (con disciplina profesional: color en superficies y cifras, nunca en el texto largo).

## Macrostructure family
- Catálogo público: Bento Grid (tarjetas de color, ritmo por tintes rotativos).
- Panel (app): app shell con rail en píldoras (móvil: barra inferior de 5 pestañas). Sin enriquecimiento: la función lleva la página.

## Theme (`frontend/app/tokens.css`)
- Papel `--color-paper` oklch(41% .100 154) · `-2` oklch(47% .105 154) · `-3` oklch(34% .090 156)
- Texto `--color-ink` oklch(99% .005 90) · `-2` oklch(94% .020 120) · `--color-muted` oklch(90% .030 150)
- Acento `--color-accent` oklch(83% .115 56) (durazno) · `--color-accent-2` oklch(74% .150 46)
- Tarjeta crema `--color-card` oklch(97% .012 85) con tinta `--color-card-ink` oklch(24% .050 160); acento sobre crema `--color-card-accent` oklch(52% .160 42)
- Tintes `--color-tint-1..4`: durazno, mantequilla, menta, cielo (misma luminosidad ≈ 86–91 %)
- Las superficies de tarjeta remapean `--color-paper/ink/accent…` a los `--color-card-*` en `squeeze.css`: los componentes se escriben una vez.

## Typography
- Display: Gabarito 800 (roman, nunca cursiva) · Cuerpo: Manrope 500/700/800 · Sin tercera familia (los códigos `IMP-0001` van en Gabarito con espaciado).
- Tracking de display −0.025 em.

## Spacing / Motion
Escala de 4 pt en tokens. Easings `--ease-out` etc.; hover de tarjetas −6 px + sombra; botones «se hunden 3 px» al pulsar; `prefers-reduced-motion` anula transformaciones.

## CTA voice
Píldora (radio 999) en 48 px de alto; primario = crema/verde sobre papel y verde oscuro sobre tarjeta; acento = durazno sobre papel y naranja profundo sobre tarjeta, con borde inferior de 3 px que se aplasta al pulsar.

## What pages MUST share
Wordmark «Mis impresiones», Gabarito + Manrope, tarjetas de 24 px de radio con sombra suave, píldoras, acento ≤ 5 % del viewport, tintes solo en fotos pendientes y cifras.

## Exports
`frontend/app/tokens.css` es la fuente. «Capas de impresión» (líneas horizontales que se desvanecen en la cabecera del catálogo) es el único adorno: alude a las capas de una pieza 3D.
