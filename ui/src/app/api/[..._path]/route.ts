import { initApiPassthrough } from "langgraph-nextjs-api-passthrough";

// This file acts as a proxy for requests to your LangGraph server.
// Read the [Going to Production](https://github.com/langchain-ai/agent-chat-ui?tab=readme-ov-file#going-to-production) section for more information.

export const { GET, POST, PUT, PATCH, DELETE, OPTIONS, runtime } =
  initApiPassthrough({
    apiUrl: process.env.LANGGRAPH_API_URL ?? "remove-me", // default, if not defined it will attempt to read process.env.LANGGRAPH_API_URL
    apiKey: process.env.LANGSMITH_API_KEY ?? "remove-me", // default, if not defined it will attempt to read process.env.LANGSMITH_API_KEY
    runtime: "edge", // default
    headers: (req) => {
      const headers: Record<string, string> = {};
      // Forward client IP and country headers
      if (req.headers.get("X-Client-IP")) headers["X-Client-IP"] = req.headers.get("X-Client-IP")!;
      if (req.headers.get("X-Client-Country")) headers["X-Client-Country"] = req.headers.get("X-Client-Country")!;
      // Forward common proxy headers
      if (req.headers.get("x-forwarded-for")) headers["x-forwarded-for"] = req.headers.get("x-forwarded-for")!;
      if (req.headers.get("x-real-ip")) headers["x-real-ip"] = req.headers.get("x-real-ip")!;
      if (req.headers.get("cf-connecting-ip")) headers["cf-connecting-ip"] = req.headers.get("cf-connecting-ip")!;
      return headers;
    },
  });
