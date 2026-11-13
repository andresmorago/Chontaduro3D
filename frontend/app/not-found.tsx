import Link from "next/link";

export default function NoEncontrada() {
  return (
    <main id="contenido" className="entrar">
      <div className="entrar__tarjeta">
        <h1>No encontramos esa página</h1>
        <p className="muted">Puede que el enlace esté mal escrito o que ya no exista.</p>
        <Link className="btn btn--primary" href="/">
          Ir al catálogo
        </Link>
      </div>
    </main>
  );
}
