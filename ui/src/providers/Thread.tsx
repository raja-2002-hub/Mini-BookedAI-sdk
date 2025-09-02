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


interface ThreadContextType {
  getThreads: () => Promise<Thread[]>;
  threads: Thread[];
  setThreads: Dispatch<SetStateAction<Thread[]>>;
  threadsLoading: boolean;
  setThreadsLoading: Dispatch<SetStateAction<boolean>>;
  currentUser: any | null;
}

const ThreadContext = createContext<ThreadContextType | undefined>(undefined);

function getThreadSearchMetadata(
  assistantId: string,
): { graph_id: string } | { assistant_id: string } {
  if (validate(assistantId)) {
    return { assistant_id: assistantId };
  } else {
    return { graph_id: assistantId };
  }
}

export function ThreadProvider({ 
  children, 
  currentUser 
}: { 
  children: ReactNode;
  currentUser: any | null;
}) {
  const [apiUrl] = useQueryState("apiUrl");
  const [assistantId] = useQueryState("assistantId");
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);

  const getThreads = useCallback(async (): Promise<Thread[]> => {
    if (!apiUrl || !assistantId || !currentUser) return [];
    const client = createClient(apiUrl, getApiKey() ?? undefined);

    console.log("[THREAD SEARCH] Current user:", currentUser.uid, currentUser.email);

    // First, search for threads with user-specific metadata
    let threads = await client.threads.search({
      metadata: {
        ...getThreadSearchMetadata(assistantId),
        user_id: currentUser.uid,
        user_email: currentUser.email || currentUser.uid,
      },
      limit: 100,
    });

    console.log("[THREAD SEARCH] Found threads with user metadata:", threads.length);

    // If no threads found with user metadata, try to find threads without user metadata
    // but only if they have messages AND were created by the current user
    if (threads.length === 0) {
      console.log("[THREAD SEARCH] No threads with user metadata, searching for threads without user metadata");
      
      const allThreads = await client.threads.search({
        metadata: {
          ...getThreadSearchMetadata(assistantId),
        },
        limit: 100,
      });

      console.log("[THREAD SEARCH] Found total threads:", allThreads.length);

      // Only show threads that have messages AND were created by the current user
      // We can't easily determine this without user metadata, so for now we'll be more restrictive
      // Only show threads if the current user is NOT a guest (to avoid showing guest conversations)
      if (!currentUser.isAnonymous) {
        threads = allThreads.filter(thread => {
          const hasMessages = !!thread.values;
          console.log(`[THREAD SEARCH] Thread ${thread.thread_id}: has_messages=${hasMessages}, metadata=${thread.metadata}`);
          return hasMessages;
        });
        console.log("[THREAD SEARCH] Filtered threads with messages (non-guest user):", threads.length);
      } else {
        console.log("[THREAD SEARCH] Guest user - not showing threads without user metadata");
        threads = [];
      }
    }

    console.log("[THREAD SEARCH] Final thread details:", threads.map(t => ({
      id: t.thread_id,
      metadata: t.metadata,
      has_messages: !!t.values,
      created_at: t.created_at
    })));

    return threads;
  }, [apiUrl, assistantId, currentUser]);

  const value = {
    getThreads,
    threads,
    setThreads,
    threadsLoading,
    setThreadsLoading,
    currentUser,
  };

  return (
    <ThreadContext.Provider value={value}>{children}</ThreadContext.Provider>
  );
}

export function useThreads() {
  const context = useContext(ThreadContext);
  if (context === undefined) {
    throw new Error("useThreads must be used within a ThreadProvider");
  }
  return context;
}
