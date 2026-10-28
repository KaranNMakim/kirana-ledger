import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Nav } from "../components/Nav";
import { Header } from "../components/Header";

export const metadata: Metadata = {
  title: "Kirana Ledger",
  description: "Voice-first udhaar ledger. Demo with synthetic data.",
  manifest: "/app/manifest.webmanifest",
  icons: { icon: "/app/icon.svg" },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#b45309" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-dvh antialiased">
        <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col">
          <Header />
          <main className="flex-1 px-4 pb-28 pt-3">{children}</main>
          <Nav />
        </div>
      </body>
    </html>
  );
}
