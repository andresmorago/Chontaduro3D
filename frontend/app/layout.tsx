import type { Metadata, Viewport } from "next";
import { Gabarito, Manrope } from "next/font/google";
import { headers } from "next/headers";
import { ProveedorAvisos } from "@/components/ui/Avisos";
import "./globals.css";

const gabarito = Gabarito({ subsets: ["latin"], weight: ["700", "800"], variable: "--font-gabarito", display: "swap" });
const manrope = Manrope({ subsets: ["latin"], weight: ["500", "700", "800"], variable: "--font-manrope", display: "swap" });

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
