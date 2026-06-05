import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Notas de Devolucao",
  description: "Operacao de notas fiscais de entrada de devolucao em lote"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}

