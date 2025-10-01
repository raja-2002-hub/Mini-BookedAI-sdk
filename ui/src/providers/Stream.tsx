"use client";

import React, {
  createContext,
  useContext,
  ReactNode,
  useState,
  useEffect,
} from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import { type Message } from "@langchain/langgraph-sdk";
import {
  uiMessageReducer,
  isUIMessage,
  isRemoveUIMessage,
  type UIMessage,
  type RemoveUIMessage,
} from "@langchain/langgraph-sdk/react-ui";
import { useQueryState } from "nuqs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { BookedLogoSVG } from "@/components/icons/booked";
import { Label } from "@/components/ui/label";
import { ArrowRight } from "lucide-react";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { PasswordInput } from "@/components/ui/password-input";
import { getApiKey } from "@/lib/api-key";
import { useThreads } from "./Thread";
import { toast } from "sonner";
import { DO_NOT_RENDER_ID_PREFIX } from "@/lib/ensure-tool-responses";
import { useAuth, useUser } from "@clerk/nextjs";


export type StateType = { messages: Message[]; ui?: UIMessage[] };

const useTypedStream = useStream<
  StateType,
  {
    UpdateType: {
      messages?: Message[] | Message | string;
      ui?: (UIMessage | RemoveUIMessage)[] | UIMessage | RemoveUIMessage;
      context?: Record<string, unknown>;
    };
    CustomEventType: UIMessage | RemoveUIMessage;
  }
>;

type StreamContextType = ReturnType<typeof useTypedStream>;
const StreamContext = createContext<StreamContextType | undefined>(undefined);

async function sleep(ms = 4000) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function checkGraphStatus(
  apiUrl: string,
  apiKey: string | null,
): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/info`, {
      ...(apiKey && {
        headers: {
          "X-Api-Key": apiKey,
        },
      }),
    });

    return res.ok;
  } catch (e) {
    console.error(e);
    return false;
  }
}

const StreamSession = ({
  children,
  apiKey,
  apiUrl,
  assistantId,
}: {
  children: ReactNode;
  apiKey: string | null;
  apiUrl: string;
  assistantId: string;
}) => {
  // Resolve absolute API base to avoid SDK URL errors
  const apiBase = typeof window !== "undefined" ? `${window.location.origin}/api` : "/api";
  const [threadId, setThreadId] = useQueryState("threadId");
  const { getThreads, setThreads } = useThreads();
  const [clientMeta, setClientMeta] = useState<{ ip?: string; country?: string }>({});
  const { isSignedIn, userId, isLoaded: authLoaded } = useAuth();
  const { user, isLoaded: userLoaded } = useUser();

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("https://ipapi.co/json");
        if (res.ok) {
          const data = await res.json();
          setClientMeta({ ip: data?.ip, country: data?.country });
        }
      } catch (error) {
        console.warn("Failed to fetch client metadata:", error);
      } finally {
        // Fallback: derive country from browser locale/timezone if IP API fails
        try {
          const hasCountry = Boolean(clientMeta.country);
          if (!hasCountry && typeof navigator !== 'undefined') {
            const lang = navigator.language;
            const viaLang = (lang && /-[A-Z]{2}/i.test(lang)) ? lang.slice(-2).toUpperCase() : undefined;
            const tz = typeof Intl !== 'undefined' && (Intl as any).DateTimeFormat ? (Intl as any).DateTimeFormat().resolvedOptions().timeZone : undefined;
            const viaTz = tz && /Australia\//.test(tz) ? 'AU' : undefined;
            const cc = viaLang || viaTz;
            if (cc) setClientMeta((prev) => ({ ...prev, country: prev.country || cc }));
          }
        } catch {}
      }
    })();
  }, []);

  // No URL user_id injection; proxy resolves via Clerk on server

  // Always go through Next.js API passthrough so headers are preserved server-side
  const streamValue = useTypedStream({
    apiUrl: apiBase,
    apiKey: apiKey ?? undefined,
    assistantId,
    threadId: threadId ?? null,
    defaultHeaders: (clientMeta.country
      ? { "X-Client-Country": clientMeta.country }
      : undefined) as any,
    onCustomEvent: (event, options) => {
      
      if (isUIMessage(event) || isRemoveUIMessage(event)) {
        
        options.mutate((prev) => {
          const ui = uiMessageReducer(prev.ui ?? [], event);
          return { ...prev, ui };
        });
        
        console.log("[STREAM] ✓ UI message processed successfully");
      } else {
        console.log("[STREAM] Non-UI custom event received");
      }
    },
    onThreadId: (id) => {
      setThreadId(id);
      // Refetch threads list when thread ID changes.
      // Wait for some seconds before fetching so we're able to get the new thread that was created.
      sleep().then(() => getThreads().then(setThreads).catch(console.error));
    },
  });

  // Inject client_country and user context into every submit context so the model can use it in tool calls
  const value = {
    ...streamValue,
    submit: (
      params?: { messages?: any; context?: Record<string, unknown> },
      options?: any,
    ) => {
      // Only pass non-sensitive context data through message context
      // Authentication is handled exclusively through headers for security
      const contextData: Record<string, unknown> = {};
      if (clientMeta.country) {
        contextData.client_country = clientMeta.country;
      } else if (typeof navigator !== 'undefined') {
        const lang = navigator.language;
        const cc = (lang && /-[A-Z]{2}/i.test(lang)) ? lang.slice(-2).toUpperCase() : undefined;
        if (cc) contextData.client_country = cc;
      }

      const merged = params
        ? {
            ...params,
            context: {
              ...(params.context || {}),
              ...contextData,
            },
          }
        : params;

      // Also inject into run config so tools can read from configurable
      const updatedOptions = {
        ...(options || {}),
        headers: {
          ...((options && (options as any).headers) || {}),
          ...(contextData.client_country ? { "X-Client-Country": contextData.client_country as string } : {}),
        },
        config: {
          ...((options && options.config) || {}),
          configurable: {
            ...(((options && options.config && options.config.configurable) || {})),
            ...(contextData.client_country ? { client_country: contextData.client_country } : {}),
          },
        },
      };

      return streamValue.submit(merged as any, updatedOptions);
    },
  } as typeof streamValue;

  useEffect(() => {
    checkGraphStatus(apiBase, apiKey).then((ok) => {
      if (!ok) {
        toast.error("Failed to connect to LangGraph server", {
          description: () => (
            <p>
              Please ensure your graph is running at <code>{apiBase}</code> and
              your API key is correctly set (if connecting to a deployed graph).
            </p>
          ),
          duration: 10000,
          richColors: true,
          closeButton: true,
        });
      }
    });
  }, [apiKey, apiBase]);

  return (
    <StreamContext.Provider value={value}>
      {children}
    </StreamContext.Provider>
  );
};

// Default values for the form
const DEFAULT_API_URL = "http://localhost:2024";
const DEFAULT_ASSISTANT_ID = "agent";

export const StreamProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  // Get environment variables
  const envApiUrl: string | undefined = process.env.NEXT_PUBLIC_API_URL;
  const envAssistantId: string | undefined =
    process.env.NEXT_PUBLIC_ASSISTANT_ID;

  // Use URL params with env var fallbacks
  const [apiUrl, setApiUrl] = useQueryState("apiUrl", {
    defaultValue: envApiUrl || "",
  });
  const [assistantId, setAssistantId] = useQueryState("assistantId", {
    defaultValue: envAssistantId || "",
  });

  // For API key, use localStorage with env var fallback
  const [apiKey, _setApiKey] = useState(() => {
    const storedKey = getApiKey();
    return storedKey || "";
  });

  const setApiKey = (key: string) => {
    window.localStorage.setItem("lg:chat:apiKey", key);
    _setApiKey(key);
  };

  // Determine final values to use, prioritizing URL params then env vars
  const finalApiUrl = apiUrl || envApiUrl;
  const finalAssistantId = assistantId || envAssistantId;

  // Show the form if we: don't have an API URL, or don't have an assistant ID
  if (!finalApiUrl || !finalAssistantId) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center p-4">
        <div className="animate-in fade-in-0 zoom-in-95 bg-background flex max-w-3xl flex-col rounded-lg border shadow-lg relative">
          <div className="absolute top-4 right-4">
            <ThemeSwitcher />
          </div>
          <div className="mt-14 flex flex-col gap-2 border-b p-6">
            <div className="flex flex-col items-start gap-4">
              <BookedLogoSVG height={48} />
            </div>
            <p className="text-muted-foreground">
              Welcome! Before you get started, you need to enter
              the URL of the deployment and the assistant / graph ID.
            </p>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();

              const form = e.target as HTMLFormElement;
              const formData = new FormData(form);
              const apiUrl = formData.get("apiUrl") as string;
              const assistantId = formData.get("assistantId") as string;
              const apiKey = formData.get("apiKey") as string;

              setApiUrl(apiUrl);
              setApiKey(apiKey);
              setAssistantId(assistantId);

              form.reset();
            }}
            className="bg-muted/50 flex flex-col gap-6 p-6"
          >
            <div className="flex flex-col gap-2">
              <Label htmlFor="apiUrl">
                Deployment URL<span className="text-rose-500">*</span>
              </Label>
              <p className="text-muted-foreground text-sm">
                This is the URL of your LangGraph deployment. Can be a local, or
                production deployment.
              </p>
              <Input
                id="apiUrl"
                name="apiUrl"
                className="bg-background"
                defaultValue={apiUrl || DEFAULT_API_URL}
                required
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="assistantId">
                Assistant / Graph ID<span className="text-rose-500">*</span>
              </Label>
              <p className="text-muted-foreground text-sm">
                This is the ID of the graph (can be the graph name), or
                assistant to fetch threads from, and invoke when actions are
                taken.
              </p>
              <Input
                id="assistantId"
                name="assistantId"
                className="bg-background"
                defaultValue={assistantId || DEFAULT_ASSISTANT_ID}
                required
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="apiKey">LangSmith API Key</Label>
              <p className="text-muted-foreground text-sm">
                This is <strong>NOT</strong> required if using a local LangGraph
                server. This value is stored in your browser's local storage and
                is only used to authenticate requests sent to your LangGraph
                server.
              </p>
              <PasswordInput
                id="apiKey"
                name="apiKey"
                defaultValue={apiKey ?? ""}
                className="bg-background"
                placeholder="lsv2_pt_..."
              />
            </div>

            <div className="mt-2 flex justify-end">
              <Button
                type="submit"
                size="lg"
              >
                Continue
                <ArrowRight className="size-5" />
              </Button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  return (
    <StreamSession
      apiKey={apiKey}
      apiUrl={apiUrl}
      assistantId={assistantId}
    >
      {children}
    </StreamSession>
  );
};

// Create a custom hook to use the context
export const useStreamContext = (): StreamContextType => {
  const context = useContext(StreamContext);
  if (context === undefined) {
    throw new Error("useStreamContext must be used within a StreamProvider");
  }
  return context;
};

export default StreamContext;
