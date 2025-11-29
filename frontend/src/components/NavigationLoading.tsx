"use client";

import { useEffect, useState, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import LoadingScreen from "./LoadingScreen";

const MIN_DISPLAY_TIME = 1500; // 1.5 seconds minimum display time

export default function NavigationLoading() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isLoading, setIsLoading] = useState(false);
  const loadingStartTimeRef = useRef<number | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // Reset loading state when route changes, but ensure minimum display time
    if (loadingStartTimeRef.current) {
      const elapsed = Date.now() - loadingStartTimeRef.current;
      const remaining = Math.max(0, MIN_DISPLAY_TIME - elapsed);
      
      if (remaining > 0) {
        timeoutRef.current = setTimeout(() => {
          setIsLoading(false);
          loadingStartTimeRef.current = null;
        }, remaining);
      } else {
        setIsLoading(false);
        loadingStartTimeRef.current = null;
      }
    }
  }, [pathname, searchParams]);

  useEffect(() => {
    // Show loading when clicking links
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      const link = target.closest("a");
      
      if (link && link.href) {
        const url = new URL(link.href);
        // Only show loading for internal navigation
        if (url.origin === window.location.origin && url.pathname !== pathname) {
          loadingStartTimeRef.current = Date.now();
          setIsLoading(true);
        }
      }
    };

    document.addEventListener("click", handleClick);
    return () => {
      document.removeEventListener("click", handleClick);
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [pathname]);

  if (!isLoading) return null;

  return <LoadingScreen />;
}

