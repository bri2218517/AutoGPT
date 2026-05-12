import {
  useGetV2GetSharedChat,
  useGetV2GetSharedChatMessages,
} from "@/app/api/__generated__/endpoints/chat/chat";

const PAGE_SIZE = 200;

// Retry transient failures, but not real 404s — a missing share is a
// permanent state and looping retries on it would just delay the error
// UI without changing the outcome.
function retryUnlessNotFound(failureCount: number, error: unknown): boolean {
  const status = (error as { status?: number } | null)?.status;
  if (status === 404) return false;
  return failureCount < 3;
}

export function useSharedChatPage(token: string) {
  const sessionQuery = useGetV2GetSharedChat(token, {
    query: {
      retry: retryUnlessNotFound,
      select: (res) => (res.status === 200 ? res.data : undefined),
    },
  });

  const messagesQuery = useGetV2GetSharedChatMessages(
    token,
    { limit: PAGE_SIZE },
    {
      query: {
        enabled: !!sessionQuery.data,
        retry: retryUnlessNotFound,
        select: (res) => (res.status === 200 ? res.data : undefined),
      },
    },
  );

  const isLoading = sessionQuery.isLoading || messagesQuery.isLoading;
  const isError = sessionQuery.isError || messagesQuery.isError;
  const rawError = sessionQuery.error || messagesQuery.error;
  const error = rawError instanceof Error ? rawError.message : undefined;

  return {
    session: sessionQuery.data,
    messages: messagesQuery.data?.messages ?? [],
    hasMore: messagesQuery.data?.has_more ?? false,
    isLoading,
    isError,
    error,
    retry: () => {
      sessionQuery.refetch();
      messagesQuery.refetch();
    },
  };
}
