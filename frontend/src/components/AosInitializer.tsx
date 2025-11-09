"use client";

import { useEffect } from "react";

export default function AosInitializer(): null {
  useEffect(() => {
    const load = async () => {
      const AOS = (await import("aos")).default;
      AOS.init({
        once: true,
        duration: 700,
        easing: "ease-out-cubic",
        offset: 60
      });
    };

    void load();
  }, []);

  return null;
}

