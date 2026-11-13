import { Catalogo } from "@/components/publico/Catalogo";
import { api } from "@/lib/api";
import type { CatalogoPublico } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function Inicio() {
  let catalogo: CatalogoPublico = { articulos: [], whatsapp_negocio: "" };
  try {
    catalogo = await api.publico.catalogo();
  } catch {
    // Si la API no responde se muestra el catálogo vacío, no una página rota.
  }
  const negocio = process.env.NOMBRE_NEGOCIO || "Mis impresiones";
  return <Catalogo articulos={catalogo.articulos} whatsapp={catalogo.whatsapp_negocio} negocio={negocio} />;
}
