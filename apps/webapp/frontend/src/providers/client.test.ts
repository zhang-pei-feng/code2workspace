import { describe, expect, test, vi } from "vitest";

const clientSpy = vi.fn();

vi.mock("@langchain/langgraph-sdk", () => ({
  Client: function MockClient(config: unknown) {
    clientSpy(config);
    return { config };
  },
}));

describe("createClient", () => {
  test("resolves same-origin relative api urls before constructing the SDK client", async () => {
    vi.stubGlobal("window", {
      location: { origin: "http://localhost:3000" },
    });
    const { createClient } = await import("./client");

    createClient("/langgraph", undefined, undefined);

    expect(clientSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        apiUrl: "http://localhost:3000/langgraph",
      }),
    );

    vi.unstubAllGlobals();
  });
});
