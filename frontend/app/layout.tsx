import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Onest, Syne } from "next/font/google";
import { headers } from "next/headers";
import { ProveedorAvisos } from "@/components/ui/Avisos";
import "./globals.css";

const syne = Syne({ subsets: ["latin"], weight: ["700"], variable: "--font-syne", display: "swap" });
const onest = Onest({ subsets: ["latin"], weight: ["400", "500", "700"], variable: "--font-onest", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["500"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Piezas impresas en 3D", template: "%s · Impresiones 3D" },
  description: "Catálogo de piezas impresas en 3D. Elige lo que te gusta y haz tu pedido.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Leer la cabecera hace dinámico el render: Next añade el nonce de la CSP a sus scripts.
  await headers();
  return (
    <html lang="es" className={`${syne.variable} ${onest.variable} ${mono.variable}`}>
      <body>
        <a className="skip" href="#contenido">
          Saltar al contenido
        </a>
        <ProveedorAvisos>{children}</ProveedorAvisos>
      </body>
    </html>
  );
}
