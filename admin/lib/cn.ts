import clsx, { type ClassValue } from "clsx";

/** Concatena classes condicionais (fino wrapper sobre clsx). */
export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}
