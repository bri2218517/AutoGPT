import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@/tests/integrations/test-utils";
import OnboardingPage from "../page";
import { useOnboardingWizardStore } from "../store";

vi.mock("../steps/WelcomeStep", () => ({
  WelcomeStep: () => <div data-testid="step-welcome" />,
}));
vi.mock("../steps/RoleStep", () => ({
  RoleStep: () => <div data-testid="step-role" />,
}));
vi.mock("../steps/PainPointsStep", () => ({
  PainPointsStep: () => <div data-testid="step-painpoints" />,
}));
vi.mock("../steps/SubscriptionStep/SubscriptionStep", () => ({
  SubscriptionStep: () => <div data-testid="step-subscription" />,
}));
vi.mock("../steps/PreparingStep", () => ({
  PreparingStep: ({ onComplete }: { onComplete: () => void }) => (
    <div data-testid="step-preparing">
      <button data-testid="preparing-finish" onClick={onComplete}>
        finish
      </button>
    </div>
  ),
}));

let currentSearchParams = new URLSearchParams();
const routerReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: routerReplace,
    push: vi.fn(),
    refresh: vi.fn(),
  }),
  useSearchParams: () => currentSearchParams,
  usePathname: () => "/onboarding",
}));

vi.mock("@/lib/supabase/hooks/useSupabase", () => ({
  useSupabase: () => ({ isLoggedIn: true, isUserLoading: false, user: null }),
}));

const completeStepMock = vi.fn();
const submitProfileMock = vi.fn();
vi.mock("@/app/api/__generated__/endpoints/onboarding/onboarding", () => ({
  getV1OnboardingState: () =>
    Promise.resolve({ status: 200, data: { completedSteps: [] } }),
  getV1CheckIfOnboardingIsCompleted: () =>
    Promise.resolve({ status: 200, data: false }),
  patchV1UpdateOnboardingState: () => Promise.resolve({ status: 200 }),
  postV1CompleteOnboardingStep: (body: unknown) => completeStepMock(body),
  postV1SubmitOnboardingProfile: (body: unknown) => submitProfileMock(body),
}));

vi.mock("@/app/api/helpers", () => ({
  resolveResponse: (p: Promise<{ data: unknown }>) => p.then((r) => r.data),
}));

let mockFlagValue = false;
vi.mock("@/services/feature-flags/use-get-flag", () => ({
  Flag: { ENABLE_PLATFORM_PAYMENT: "ENABLE_PLATFORM_PAYMENT" },
  useGetFlag: () => mockFlagValue,
}));

vi.mock("launchdarkly-react-client-sdk", () => ({
  useLDClient: () => ({
    waitForInitialization: () => Promise.resolve(),
  }),
}));

beforeEach(() => {
  currentSearchParams = new URLSearchParams();
  mockFlagValue = false;
  routerReplace.mockClear();
  completeStepMock.mockClear();
  completeStepMock.mockReturnValue(Promise.resolve({ status: 200 }));
  submitProfileMock.mockClear();
  submitProfileMock.mockReturnValue(Promise.resolve({ status: 200 }));
  useOnboardingWizardStore.getState().reset();
});

afterEach(() => {
  cleanup();
});

describe("OnboardingPage — flag-gated SubscriptionStep", () => {
  it("renders Welcome at step 1 by default in flag-off mode", async () => {
    mockFlagValue = false;
    render(<OnboardingPage />);
    expect(await screen.findByTestId("step-welcome")).toBeDefined();
    expect(screen.queryByTestId("step-subscription")).toBeNull();
  });

  it("clamps ?step=5 to step 1 when payments are gated off", async () => {
    mockFlagValue = false;
    currentSearchParams = new URLSearchParams("step=5");
    render(<OnboardingPage />);
    expect(await screen.findByTestId("step-welcome")).toBeDefined();
    expect(screen.queryByTestId("step-preparing")).toBeNull();
  });

  it("treats step 4 as Preparing when payments are gated off", async () => {
    mockFlagValue = false;
    currentSearchParams = new URLSearchParams("step=4");
    render(<OnboardingPage />);
    expect(await screen.findByTestId("step-preparing")).toBeDefined();
    expect(screen.queryByTestId("step-subscription")).toBeNull();
  });

  it("renders SubscriptionStep at step 4 when payments are enabled", async () => {
    mockFlagValue = true;
    currentSearchParams = new URLSearchParams("step=4");
    render(<OnboardingPage />);
    expect(await screen.findByTestId("step-subscription")).toBeDefined();
    expect(screen.queryByTestId("step-preparing")).toBeNull();
  });

  it("treats step 5 as Preparing when payments are enabled", async () => {
    mockFlagValue = true;
    currentSearchParams = new URLSearchParams("step=5");
    render(<OnboardingPage />);
    expect(await screen.findByTestId("step-preparing")).toBeDefined();
    expect(screen.queryByTestId("step-subscription")).toBeNull();
  });

  it("rejects decimal step values and falls back to step 1", async () => {
    mockFlagValue = true;
    currentSearchParams = new URLSearchParams("step=2.5");
    render(<OnboardingPage />);
    expect(await screen.findByTestId("step-welcome")).toBeDefined();
    expect(screen.queryByTestId("step-role")).toBeNull();
  });

  it("rejects non-numeric step values and falls back to step 1", async () => {
    mockFlagValue = true;
    currentSearchParams = new URLSearchParams("step=foo");
    render(<OnboardingPage />);
    expect(await screen.findByTestId("step-welcome")).toBeDefined();
  });

  it("submits the profile after the user advances into Preparing", async () => {
    mockFlagValue = false;
    currentSearchParams = new URLSearchParams("step=1");
    render(<OnboardingPage />);
    expect(await screen.findByTestId("step-welcome")).toBeDefined();
    await act(async () => {
      useOnboardingWizardStore.setState({
        name: "Avery",
        role: "Engineering",
        painPoints: ["Research", "Something else"],
        otherPainPoint: "  drafting status updates  ",
      });
      useOnboardingWizardStore.getState().goToStep(4);
    });
    expect(await screen.findByTestId("step-preparing")).toBeDefined();
    await waitFor(() => expect(submitProfileMock).toHaveBeenCalledTimes(1));
    expect(submitProfileMock).toHaveBeenCalledWith({
      user_name: "Avery",
      user_role: "Engineering",
      pain_points: ["Research", "drafting status updates"],
    });
  });

  it("redirects to /copilot when handlePreparingComplete fires", async () => {
    mockFlagValue = false;
    currentSearchParams = new URLSearchParams("step=4");
    render(<OnboardingPage />);
    const finish = await screen.findByTestId("preparing-finish");
    await act(async () => {
      fireEvent.click(finish);
    });
    await waitFor(() => expect(completeStepMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith("/copilot"));
  });

  it("syncs URL when the store advances past the URL step", async () => {
    mockFlagValue = false;
    currentSearchParams = new URLSearchParams("step=1");
    render(<OnboardingPage />);
    expect(await screen.findByTestId("step-welcome")).toBeDefined();
    await act(async () => {
      useOnboardingWizardStore.getState().goToStep(3);
    });
    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith("/onboarding?step=3", {
        scroll: false,
      }),
    );
  });
});
