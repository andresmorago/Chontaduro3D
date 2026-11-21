import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { headers } from "next/headers";
import { ProveedorAvisos } from "@/components/ui/Avisos";
import "./globals.css";

// Fuentes alojadas en el repositorio (variables, subconjunto latino; licencia OFL): el build no depende de Google Fonts.
// Antes se descargaban al compilar con next/font/google y el build fallaba si Google respondía algo inesperado.
const gabarito = localFont({ src: "./fonts/gabarito-latin.woff2", weight: "400 900", variable: "--font-gabarito", display: "swap" });
const manrope = localFont({ src: "./fonts/manrope-latin.woff2", weight: "200 800", variable: "--font-manrope", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Piezas impresas en 3D", template: "%s · Impresiones 3D" },
  description: "Catálogo de piezas impresas en 3D. Elige lo que te gusta y haz tu pedido.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Leer la cabecera hace dinámico el render: Next añade el nonce de la CSP a sus scripts.
  await headers();
  return (
    <html lang="es" className={`${gabarito.variable} ${manrope.variable}`}>
      <body>
        <a className="skip" href="#contenido">
          Saltar al contenido
        </a>
        <ProveedorAvisos>{children}</ProveedorAvisos>
      </body>
    </html>
  );
}
