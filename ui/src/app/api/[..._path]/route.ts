import { initApiPassthrough } from "langgraph-nextjs-api-passthrough";

// This file acts as a proxy for requests to your LangGraph server.
// Read the [Going to Production](https://github.com/langchain-ai/agent-chat-ui?tab=readme-ov-file#going-to-production) section for more information.

export const { GET, POST, PUT, PATCH, DELETE, OPTIONS, runtime } =
  initApiPassthrough({
    apiUrl: process.env.LANGGRAPH_API_URL ?? "remove-me", // default, if not defined it will attempt to read process.env.LANGGRAPH_API_URL
    apiKey: process.env.LANGSMITH_API_KEY ?? "remove-me", // default, if not defined it will attempt to read process.env.LANGSMITH_API_KEY
    runtime: "edge", // default
    // Forward custom headers
    forwardHeaders: [
      "X-User-ID",
      "X-User-Email",
      "X-Client-IP",
      "X-Client-Country",
      // Common proxy client IP headers (in case your deployment sets them)
      "x-forwarded-for",
      "x-real-ip",
      "cf-connecting-ip",
    ],
  });
