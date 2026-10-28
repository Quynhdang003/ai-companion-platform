import { z } from "zod";
import {
  elderSchema,
  errorBodySchema,
  incomingRequestSchema,
  linkRequestDecisionSchema,
  outgoingRequestSchema,
  registrationSchema,
  userSchema,
  type ElderCreate,
} from "./schemas";

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

type RequestOptions = { method?: "GET" | "POST"; json?: unknown };

async function request<T>(
  getToken: GetToken,
  path: string,
  schema: z.ZodType<T>,
  { method = "GET", json }: RequestOptions = {},
): Promise<T> {
  const headers = new Headers();
  const token = await getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${apiBaseUrl()}${path}`, {
    method,
    headers,
    body: json === undefined ? undefined : JSON.stringify(json),
  });
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
    listElders: () => request(getToken, "/api/elders", z.array(elderSchema)),
    createElder: (body: ElderCreate) =>
      request(getToken, "/api/elders", registrationSchema, {
        method: "POST",
        json: body,
      }),
    listIncomingRequests: () =>
      request(
        getToken,
        "/api/link-requests/incoming",
        z.array(incomingRequestSchema),
      ),
    listOutgoingRequests: () =>
      request(
        getToken,
        "/api/link-requests/outgoing",
        z.array(outgoingRequestSchema),
      ),
    approveRequest: (id: string) =>
      request(
        getToken,
        `/api/link-requests/${id}/approve`,
        linkRequestDecisionSchema,
        { method: "POST" },
      ),
    rejectRequest: (id: string) =>
      request(
        getToken,
        `/api/link-requests/${id}/reject`,
        linkRequestDecisionSchema,
        { method: "POST" },
      ),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
