import {
  getV1OnboardingState,
  postV1CompleteOnboardingStep,
  postV1SubmitOnboardingProfile,
} from "@/app/api/__generated__/endpoints/onboarding/onboarding";
import { resolveResponse } from "@/app/api/helpers";
import { useSupabase } from "@/lib/supabase/hooks/useSupabase";
import { Flag, useGetFlag } from "@/services/feature-flags/use-get-flag";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Step, useOnboardingWizardStore } from "./store";

function parseStep(value: string | null, maxStep: number): Step {
  const n = Number(value);
  if (n >= 1 && n <= maxStep) return n as Step;
  return 1;
}

export function useOnboardingPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isLoggedIn } = useSupabase();
  const currentStep = useOnboardingWizardStore((s) => s.currentStep);
  const goToStep = useOnboardingWizardStore((s) => s.goToStep);
  const reset = useOnboardingWizardStore((s) => s.reset);
  const isPaymentEnabled = useGetFlag(Flag.ENABLE_PLATFORM_PAYMENT);
  const preparingStep = isPaymentEnabled ? 5 : 4;
  const [isLoading, setIsLoading] = useState(true);
  const hasSubmitted = useRef(false);
  const hasInitialized = useRef(false);

  // Initialise store from URL on mount, reset form data
  useEffect(() => {
    if (hasInitialized.current) return;
    hasInitialized.current = true;
    const urlStep = parseStep(searchParams.get("step"), preparingStep);
    reset();
    goToStep(urlStep);
  }, [searchParams, reset, goToStep, preparingStep]);

  // Sync store → URL when step changes
  useEffect(() => {
    const urlStep = parseStep(searchParams.get("step"), preparingStep);
    if (currentStep !== urlStep) {
      router.replace(`/onboarding?step=${currentStep}`, { scroll: false });
    }
  }, [currentStep, router, searchParams, preparingStep]);

  // Check if onboarding already completed
  useEffect(() => {
    if (!isLoggedIn) return;

    async function checkCompletion() {
      try {
        const onboarding = await resolveResponse(getV1OnboardingState());
        if (onboarding.completedSteps.includes("VISIT_COPILOT")) {
          router.replace("/copilot");
          return;
        }
      } catch {
        // If we can't check, show onboarding anyway
      }
      setIsLoading(false);
    }

    checkCompletion();
  }, [isLoggedIn, router]);

  // Submit profile when entering the Preparing step
  useEffect(() => {
    if (currentStep !== preparingStep || hasSubmitted.current) return;
    hasSubmitted.current = true;

    const { name, role, otherRole, painPoints, otherPainPoint } =
      useOnboardingWizardStore.getState();
    const resolvedRole = role === "Other" ? otherRole : role;
    const resolvedPainPoints = painPoints
      .filter((p) => p !== "Something else")
      .concat(
        painPoints.includes("Something else") && otherPainPoint.trim()
          ? [otherPainPoint.trim()]
          : [],
      );

    postV1SubmitOnboardingProfile({
      user_name: name,
      user_role: resolvedRole,
      pain_points: resolvedPainPoints,
    }).catch(() => {
      // Best effort — profile data is non-critical for accessing copilot
    });
  }, [currentStep, preparingStep]);

  async function handlePreparingComplete() {
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        await postV1CompleteOnboardingStep({ step: "VISIT_COPILOT" });
        router.replace("/copilot");
        return;
      } catch {
        if (attempt < 2) await new Promise((r) => setTimeout(r, 1000));
      }
    }
    router.replace("/copilot");
  }

  return {
    currentStep,
    isLoading,
    handlePreparingComplete,
  };
}
