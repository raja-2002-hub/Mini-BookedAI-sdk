import { initApiPassthrough } from "langgraph-nextjs-api-passthrough";
import { getAuth } from "@clerk/nextjs/server";

// This file acts as a proxy for requests to your LangGraph server.
// Read the [Going to Production](https://github.com/langchain-ai/agent-chat-ui?tab=readme-ov-file#going-to-production) section for more information.

export const { GET, POST, PUT, PATCH, DELETE, OPTIONS, runtime } =
  initApiPassthrough({
    apiUrl: process.env.LANGGRAPH_API_URL ?? "http://localhost:2024", // sensible local default for dev
    apiKey: process.env.LANGSMITH_API_KEY ?? "remove-me", // default, if not defined it will attempt to read process.env.LANGSMITH_API_KEY
    runtime: "nodejs",
    disableWarningLog: true, // Disable the authentication warning
    headers: (req) => {
      const headers: Record<string, string> = {};

      // No user headers; user is resolved server-side in bodyParameters

      // Minimal forwarding only + keep client IP/country for validation flows
      const { userId } = getAuth(req as any);
      if (userId) {
        headers["X-User-ID"] = userId;
        headers["X-User-Authenticated"] = "true";
        headers["X-User-Provider"] = "clerk";
      }
      if (req.headers.get("X-Client-IP")) headers["X-Client-IP"] = req.headers.get("X-Client-IP")!;
      if (req.headers.get("X-Client-Country")) headers["X-Client-Country"] = req.headers.get("X-Client-Country")!;
      if (req.headers.get("x-forwarded-for")) headers["x-forwarded-for"] = req.headers.get("x-forwarded-for")!;
      return headers;
    },
    bodyParameters: (req, body) => {
      // Minimal: only attach headers into metadata.headers
      try {
        const nextBody: any = body && typeof body === 'object' ? body : {};
        const { userId } = getAuth(req as any);

        const metaHeaders: Record<string, string> = {};
        if (userId) {
          metaHeaders['X-User-ID'] = userId;
          metaHeaders['X-User-Authenticated'] = 'true';
          metaHeaders['X-User-Provider'] = 'clerk';
        }
        const ip = req.headers.get('X-Client-IP');
        const country = req.headers.get('X-Client-Country');
        const xff = req.headers.get('x-forwarded-for');
        if (ip) metaHeaders['X-Client-IP'] = ip;
        if (country) metaHeaders['X-Client-Country'] = country;
        if (xff) metaHeaders['x-forwarded-for'] = xff;

        nextBody.metadata = nextBody.metadata || {};
        nextBody.metadata.headers = { ...(nextBody.metadata.headers || {}), ...metaHeaders };

        // Also mirror into config.configurable so the graph can always read it
        if (country) {
          nextBody.config = nextBody.config || {};
          nextBody.config.configurable = {
            ...(nextBody.config.configurable || {}),
            client_country: nextBody.config?.configurable?.client_country || country,
          };
        }

        // Ensure signed-in user flows work in dev: mirror into messages.additional_kwargs
        if (userId && nextBody.input && Array.isArray(nextBody.input.messages)) {
          for (const m of nextBody.input.messages) {
            if (m && typeof m === 'object') {
              m.additional_kwargs = m.additional_kwargs || {};
              m.additional_kwargs.user_id = userId;
              m.additional_kwargs.authenticated = true;
            }
          }
        }
        return nextBody;
      } catch {
        return body;
      }
    },
  });
