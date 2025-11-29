import { format, formatDistanceToNow } from "date-fns";
import { toZonedTime } from "date-fns-tz";

const SGT_TIMEZONE = "Asia/Singapore";

/**
 * Convert a Unix timestamp (seconds) to a Date object in SGT timezone
 */
export function timestampToSGT(timestampSeconds: number): Date {
  const utcDate = new Date(timestampSeconds * 1000);
  return toZonedTime(utcDate, SGT_TIMEZONE);
}

/**
 * Format a Unix timestamp (seconds) as a date string in SGT timezone
 */
export function formatTimestampSGT(
  timestampSeconds: number,
  formatString: string
): string {
  try {
    const sgtDate = timestampToSGT(timestampSeconds);
    return format(sgtDate, formatString);
  } catch (error) {
    // Fallback to simple locale string if formatting fails
    console.warn("Failed to format timestamp with date-fns:", error);
    return new Date(timestampSeconds * 1000).toLocaleString("en-SG", { 
      timeZone: "Asia/Singapore",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  }
}

/**
 * Format a Unix timestamp (seconds) as a relative time string in SGT timezone
 */
export function formatDistanceToNowSGT(
  timestampSeconds: number,
  options?: { addSuffix?: boolean }
): string {
  const sgtDate = timestampToSGT(timestampSeconds);
  return formatDistanceToNow(sgtDate, options);
}

