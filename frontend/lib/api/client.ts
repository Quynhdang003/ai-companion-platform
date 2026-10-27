import type { z } from "zod";
import { errorBodySchema, userSchema } from "./schemas";

/** Non-2xx backend response, carrying the backend's error `code`. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Returns the Clerk session token, or null when signed out. */
export type GetToken = () => Promise<string | null>;

function apiBaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!url) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is not set");
  }
  return url.replace(/\/+$/, "");
}

async function request<T>(
  getToken: GetToken,
  path: string,
  schema: z.ZodType<T>,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  const token = await getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${apiBaseUrl()}${path}`, { ...init, headers });
  const body: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const parsed = errorBodySchema.safeParse(body);
    if (parsed.success) {
      const { code, message } = parsed.data.error;
      throw new ApiError(response.status, code, message);
    }
    throw new ApiError(
      response.status,
      "unexpected_response",
      `Request failed with status ${response.status}`,
    );
  }
  return schema.parse(body);
}

/** Typed backend client; `getToken` decides where the Clerk token comes from. */
export function createApiClient(getToken: GetToken) {
  return {
    getMe: () => request(getToken, "/api/me", userSchema),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
