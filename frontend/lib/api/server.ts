import "server-only";
import { auth } from "@clerk/nextjs/server";
import { createApiClient, type ApiClient } from "./client";

/**
 * API client for Server Components and Server Actions, authenticated as the
 * signed-in user. Reads the request, so callers must render inside <Suspense>.
 */
export async function getServerApi(): Promise<ApiClient> {
  const { getToken } = await auth();
  return createApiClient(() => getToken());
}
