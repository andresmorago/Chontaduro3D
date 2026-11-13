interface Props {
  url: string | null;
  codigo: string;
  nombre: string;
  clase?: string;
}

/** La foto del artículo; si todavía no hay, se muestra su código (nunca una foto inventada). */
export function Foto({ url, codigo, nombre, clase }: Props) {
  return (
    <div className={["foto", clase].filter(Boolean).join(" ")}>
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt={nombre} width={600} height={600} loading="lazy" decoding="async" />
      ) : (
        <span className="foto__marca" aria-hidden="true">
          {codigo}
        </span>
      )}
    </div>
  );
}
