import { Client } from "@langchain/langgraph-sdk";

export function resolveApiUrl(apiUrl: string): string {
  if (/^https?:\/\//i.test(apiUrl)) {
    return apiUrl;
  }
  if (typeof window === "undefined") {
    return apiUrl;
  }
  return new URL(apiUrl, window.location.origin).toString();
}

export function createClient(
  apiUrl: string,
  apiKey: string | undefined,
  authScheme: string | undefined,
) {
  return new Client({
    apiKey,
    apiUrl: resolveApiUrl(apiUrl),
    ...(authScheme && {
      defaultHeaders: {
        "X-Auth-Scheme": authScheme,
      },
    }),
  });
}
