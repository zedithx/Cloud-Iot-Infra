import type { Metadata } from "next";
import "./globals.css";
import "aos/dist/aos.css";
import AosInitializer from "@/components/AosInitializer";
import ToasterProvider from "@/components/ToasterProvider";
import NavigationLoading from "@/components/NavigationLoading";

export const metadata: Metadata = {
  title: "PlantPulse",
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
        <ToasterProvider />
        <NavigationLoading />
        {children}
      </body>
    </html>
  );
}

