import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CloudIoT Telemetry Console",
  description: "Monitor and control your IoT greenhouse from anywhere."
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100">{children}</body>
    </html>
  );
}

