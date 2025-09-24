import { validate } from "uuid";
import { getApiKey } from "@/lib/api-key";
import { Thread } from "@langchain/langgraph-sdk";
import { useQueryState } from "nuqs";
import {
  createContext,
  useContext,
  ReactNode,
  useCallback,
  useState,
  Dispatch,
  SetStateAction,
} from "react";
import { createClient } from "./client";
import { useAuth } from "@clerk/nextjs";

interface ThreadContextType {
  getThreads: () => Promise<Thread[]>;
  threads: Thread[];
  setThreads: Dispatch<SetStateAction<Thread[]>>;
  threadsLoading: boolean;
  setThreadsLoading: Dispatch<SetStateAction<boolean>>;
}

const ThreadContext = createContext<ThreadContextType | undefined>(undefined);

function getThreadSearchMetadata(
  assistantId: string
): { graph_id: string } | { assistant_id: string } {
  if (validate(assistantId)) {
    return { assistant_id: assistantId };
  } else {
    return { graph_id: assistantId };
  }
}

export function ThreadProvider({ children }: { children: ReactNode }) {
  // const [apiUrl] = useQueryState("apiUrl");
  // const [assistantId] = useQueryState("assistantId");
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? null;
  const assistantId = process.env.NEXT_PUBLIC_ASSISTANT_ID ?? null;
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const { userId, isSignedIn } = useAuth();

  const getThreads = useCallback(async (): Promise<Thread[]> => {
    if (!apiUrl || !assistantId) {
      console.log("ThreadProvider: Missing apiUrl or assistantId, returning empty threads");
      return [];
    }
    const client = createClient(apiUrl, getApiKey() ?? undefined);

    try {
      const effectiveUserId = userId || "guest";

      const searchMetadata = {
        ...getThreadSearchMetadata(assistantId),
        headers: { "X-User-ID": effectiveUserId },
      };      

      const threads = await client.threads.search({
        metadata: searchMetadata,
        limit: 100,
      });

      // Fallback: If no threads are found and userId is not 'guest', try fetching without userId filter
      if (threads.length === 0 && userId && userId !== "guest") {
        console.log("ThreadProvider: No threads found for userId, attempting fallback fetch without userId filter");
        const fallbackThreads = await client.threads.search({
          metadata: {
            ...getThreadSearchMetadata(assistantId),            
          },
          limit: 100,
        });
        return fallbackThreads;
      }

      return threads;
    } catch (error) {
      console.error("ThreadProvider: Error fetching threads:", error);
      return [];
    }
  }, [apiUrl, assistantId, userId]);

  const value = {
    getThreads,
    threads,
    setThreads,
    threadsLoading,
    setThreadsLoading,
  };

  return <ThreadContext.Provider value={value}>{children}</ThreadContext.Provider>;
}

export function useThreads() {
  const context = useContext(ThreadContext);
  if (context === undefined) {
    throw new Error("useThreads must be used within a ThreadProvider");
  }
  return context;
}