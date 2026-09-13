import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Base URL of the Lens API as seen from the browser. */
export const LENS_API_URL = process.env.NEXT_PUBLIC_LENS_API_URL ?? "http://localhost:8000";

/** Base URL of the Lens API as seen from the Next.js server (inside docker compose). */
export const LENS_API_INTERNAL_URL = process.env.LENS_API_INTERNAL_URL ?? LENS_API_URL;
