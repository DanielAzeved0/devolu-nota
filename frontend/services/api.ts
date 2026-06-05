import type { HealthResponse } from "@/types/api";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function getApiHealth(): Promise<{ ok: true; data: HealthResponse } | { ok: false }> {
  try {
    const response = await fetch(`${apiBaseUrl}/health`, {
      cache: "no-store"
    });

    if (!response.ok) {
      return { ok: false };
    }

    return { ok: true, data: (await response.json()) as HealthResponse };
  } catch {
    return { ok: false };
  }
}

