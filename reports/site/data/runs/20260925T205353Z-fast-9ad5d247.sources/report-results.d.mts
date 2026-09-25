export type Result = {status: string; tests?: unknown[]; [key: string]: unknown};
export function goCases(output: string): Map<string, Result>;
export function mergeCases(...maps: Map<string, Result>[]): Map<string, Result>;
