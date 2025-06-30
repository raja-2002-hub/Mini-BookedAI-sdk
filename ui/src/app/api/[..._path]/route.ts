import { initApiPassthrough } from "langgraph-nextjs-api-passthrough";

// Add comprehensive logging for debugging UI streaming in production
console.log("[API PASSTHROUGH] Initializing at:", new Date().toISOString());
console.log("[API PASSTHROUGH] LANGGRAPH_API_URL:", process.env.LANGGRAPH_API_URL);
console.log("[API PASSTHROUGH] Has LANGSMITH_API_KEY:", !!process.env.LANGSMITH_API_KEY);

// This file acts as a proxy for requests to your LangGraph server.
// Read the [Going to Production](https://github.com/langchain-ai/agent-chat-ui?tab=readme-ov-file#going-to-production) section for more information.

export const { GET, POST, PUT, PATCH, DELETE, OPTIONS, runtime } =
  initApiPassthrough({
    apiUrl: process.env.LANGGRAPH_API_URL ?? "remove-me", // default, if not defined it will attempt to read process.env.LANGGRAPH_API_URL
    apiKey: process.env.LANGSMITH_API_KEY ?? "remove-me", // default, if not defined it will attempt to read process.env.LANGSMITH_API_KEY
    runtime: "edge", // default
  });

console.log("[API PASSTHROUGH] Successfully initialized passthrough handlers");
