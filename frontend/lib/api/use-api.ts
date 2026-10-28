"use client";

import { useMemo } from "react";
import { useAuth } from "@clerk/nextjs";
import { createApiClient, type ApiClient } from "./client";

/** API client for Client Components, authenticated with the browser's Clerk session. */
export function useApi(): ApiClient {
  const { getToken } = useAuth();
  return useMemo(() => createApiClient(() => getToken()), [getToken]);
}
