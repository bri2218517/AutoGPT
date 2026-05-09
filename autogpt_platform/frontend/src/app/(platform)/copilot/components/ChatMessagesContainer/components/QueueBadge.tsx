"use client";

import {
  getGetV2GetSessionQueryKey,
  useDeleteV2CancelQueuedTask,
} from "@/app/api/__generated__/endpoints/chat/chat";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/atoms/Tooltip/BaseTooltip";
import { toast } from "@/components/molecules/Toast/use-toast";
import * as Sentry from "@sentry/nextjs";
import {
  HourglassIcon,
  WarningCircleIcon,
  XCircleIcon,
} from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";

interface Props {
  queueStatus: "queued" | "blocked";
  queueBlockedReason?: string | null;
  /** Raw ChatMessage.id (UUID); required for the cancel endpoint. */
  rawMessageId?: string | null;
  sessionID: string | null;
}

const QUEUED_TOOLTIP =
  "Will start automatically when one of your current tasks finishes.";

export function QueueBadge({
  queueStatus,
  queueBlockedReason,
  rawMessageId,
  sessionID,
}: Props) {
  const queryClient = useQueryClient();
  const { mutate: cancelTask, isPending: isCancelling } =
    useDeleteV2CancelQueuedTask({
      mutation: {
        onSuccess: () => {
          if (sessionID) {
            queryClient.invalidateQueries({
              queryKey: getGetV2GetSessionQueryKey(sessionID),
            });
          }
          queryClient.invalidateQueries({
            queryKey: ["/api/chat/queued-tasks"],
          });
        },
        onError: (error) => {
          // 404 means the task was already promoted / not owned — sync the UI
          // with reality (the badge has stopped meaning what we thought) and
          // suppress the toast since this is expected, not an actual failure.
          const status = (error as { response?: { status?: number } })?.response
            ?.status;
          if (status === 404) {
            if (sessionID) {
              queryClient.invalidateQueries({
                queryKey: getGetV2GetSessionQueryKey(sessionID),
              });
            }
            return;
          }
          Sentry.captureException(error);
          toast({
            variant: "destructive",
            title: "Could not cancel queued task",
            description: "Please try again.",
          });
        },
      },
    });

  if (queueStatus === "blocked") {
    const reason = queueBlockedReason || "Task could not be queued.";
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-700"
            data-testid="queue-badge-blocked"
          >
            <WarningCircleIcon size={12} weight="fill" />
            Blocked
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs whitespace-normal">
          {reason}
        </TooltipContent>
      </Tooltip>
    );
  }

  function handleCancel() {
    if (!rawMessageId || isCancelling) return;
    cancelTask({ messageId: rawMessageId });
  }

  return (
    <span className="inline-flex items-center gap-1">
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className="inline-flex items-center gap-1 rounded-full bg-purple-100 px-2 py-0.5 text-[11px] font-medium text-purple-800"
            data-testid="queue-badge-queued"
          >
            <HourglassIcon size={12} weight="bold" />
            Queued
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs whitespace-normal">
          {QUEUED_TOOLTIP}
        </TooltipContent>
      </Tooltip>
      {rawMessageId ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={handleCancel}
              disabled={isCancelling}
              aria-label="Cancel queued task"
              data-testid="queue-cancel-button"
              className="inline-flex h-4 w-4 items-center justify-center rounded-full text-neutral-500 transition-colors hover:text-red-600 disabled:opacity-50"
            >
              <XCircleIcon size={14} weight="fill" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top">Cancel queued task</TooltipContent>
        </Tooltip>
      ) : null}
    </span>
  );
}
