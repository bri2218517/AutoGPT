import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  useGetSubscriptionStatus,
  useUpdateSubscriptionTier,
} from "@/app/api/__generated__/endpoints/credits/credits";
import type { SubscriptionStatusResponse } from "@/app/api/__generated__/models/subscriptionStatusResponse";
import type { SubscriptionTierRequestTier } from "@/app/api/__generated__/models/subscriptionTierRequestTier";
import { useToast } from "@/components/molecules/Toast/use-toast";

export type SubscriptionStatus = SubscriptionStatusResponse;

export function useSubscriptionTierSection() {
  const searchParams = useSearchParams();
  const subscriptionStatus = searchParams.get("subscription");
  const { toast } = useToast();
  const toastShownRef = useRef(false);
  const [tierError, setTierError] = useState<string | null>(null);

  const {
    data: subscription,
    isLoading,
    error: queryError,
    refetch,
  } = useGetSubscriptionStatus({
    query: { select: (data) => (data.status === 200 ? data.data : null) },
  });

  const fetchError = queryError ? "Failed to load subscription info" : null;

  const {
    mutateAsync: doUpdateTier,
    isPending,
    variables,
  } = useUpdateSubscriptionTier();

  useEffect(() => {
    if (subscriptionStatus === "success" && !toastShownRef.current) {
      toastShownRef.current = true;
      refetch();
      toast({
        title: "Subscription upgraded",
        description:
          "Your plan has been updated. It may take a moment to reflect.",
      });
    }
  }, [subscriptionStatus, refetch, toast]);

  async function changeTier(tier: string) {
    setTierError(null);
    try {
      const successUrl = `${window.location.origin}${window.location.pathname}?subscription=success`;
      const cancelUrl = `${window.location.origin}${window.location.pathname}?subscription=cancelled`;
      const result = await doUpdateTier({
        data: {
          tier: tier as SubscriptionTierRequestTier,
          success_url: successUrl,
          cancel_url: cancelUrl,
        },
      });
      if (result.status === 200 && result.data.url) {
        window.location.href = result.data.url;
        return;
      }
      await refetch();
    } catch (e: unknown) {
      const msg =
        e instanceof Error ? e.message : "Failed to change subscription tier";
      setTierError(msg);
    }
  }

  const pendingTier =
    isPending && variables?.data?.tier ? variables.data.tier : null;

  return {
    subscription: subscription ?? null,
    isLoading,
    error: fetchError,
    tierError,
    isPending,
    pendingTier,
    changeTier,
  };
}
