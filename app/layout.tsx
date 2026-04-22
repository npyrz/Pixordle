import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pixordle",
  description: "Reveal hidden image regions by guessing related words.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
