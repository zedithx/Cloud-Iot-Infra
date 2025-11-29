"use client";

import { useEffect, useState, useRef } from "react";
import LoadingScreen from "@/components/LoadingScreen";

const MIN_DISPLAY_TIME = 1000; // 1 second minimum display time

export default function Loading() {
  const [showLoading, setShowLoading] = useState(true);
  const startTimeRef = useRef(Date.now());

  useEffect(() => {
    // Ensure loading screen shows for at least 1 second
    const checkTime = () => {
      const elapsed = Date.now() - startTimeRef.current;
      const remaining = Math.max(0, MIN_DISPLAY_TIME - elapsed);
      
      if (remaining > 0) {
        const timer = setTimeout(() => {
          setShowLoading(false);
        }, remaining);
        return () => clearTimeout(timer);
      } else {
        setShowLoading(false);
      }
    };

    return checkTime();
  }, []);

  if (!showLoading) return null;

  return <LoadingScreen />;
}

