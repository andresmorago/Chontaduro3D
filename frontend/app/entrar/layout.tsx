import type { Metadata } from "next";

export const metadata: Metadata = { title: "Entrar", robots: { index: false, follow: false } };

export default function EntrarLayout({ children }: { children: React.ReactNode }) {
  return children;
}
