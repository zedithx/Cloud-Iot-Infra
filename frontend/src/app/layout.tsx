import type { Metadata } from "next";
import "./globals.css";
import "aos/dist/aos.css";
import AosInitializer from "@/components/AosInitializer";

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
      <body className="min-h-screen bg-plant-gradient text-slate-900">
        <AosInitializer />
        {children}
      </body>
    </html>
  );
}

