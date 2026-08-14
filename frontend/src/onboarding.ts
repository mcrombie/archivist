export const ONBOARDING_VERSION = 1 as const;
export const ONBOARDING_STORAGE_KEY = "archivist:onboarding:v1";

export type OnboardingTourStatus = "unseen" | "completed" | "skipped";
export type SourcesTipStatus = "pending" | "seen" | "skipped";

export type OnboardingState = {
  version: typeof ONBOARDING_VERSION;
  tour: OnboardingTourStatus;
  sourcesTip: SourcesTipStatus;
};

export type OnboardingStorage = Pick<Storage, "getItem" | "setItem">;

export type OnboardingStore = {
  read: () => OnboardingState;
  write: (state: OnboardingState) => OnboardingState;
};

export function initialOnboardingState(): OnboardingState {
  return {
    version: ONBOARDING_VERSION,
    tour: "unseen",
    sourcesTip: "pending"
  };
}

export function isOnboardingState(value: unknown): value is OnboardingState {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<OnboardingState>;
  return candidate.version === ONBOARDING_VERSION
    && (candidate.tour === "unseen"
      || candidate.tour === "completed"
      || candidate.tour === "skipped")
    && (candidate.sourcesTip === "pending"
      || candidate.sourcesTip === "seen"
      || candidate.sourcesTip === "skipped");
}

export function normalizeOnboardingState(value: unknown): OnboardingState {
  if (!isOnboardingState(value)) return initialOnboardingState();
  return {
    version: ONBOARDING_VERSION,
    tour: value.tour,
    sourcesTip: value.sourcesTip
  };
}

export function parseOnboardingState(serialized: string | null): OnboardingState {
  if (serialized === null) return initialOnboardingState();
  try {
    return normalizeOnboardingState(JSON.parse(serialized));
  } catch {
    return initialOnboardingState();
  }
}

export function serializeOnboardingState(state: OnboardingState): string {
  return JSON.stringify(normalizeOnboardingState(state));
}

export function completeOnboarding(state: OnboardingState): OnboardingState {
  const current = normalizeOnboardingState(state);
  return {
    ...current,
    tour: "completed"
  };
}

export function skipOnboarding(state: OnboardingState): OnboardingState {
  return {
    version: ONBOARDING_VERSION,
    tour: "skipped",
    sourcesTip: "skipped"
  };
}

export function markSourcesTipSeen(state: OnboardingState): OnboardingState {
  const current = normalizeOnboardingState(state);
  return {
    ...current,
    sourcesTip: "seen"
  };
}

export function markSourcesTipSkipped(state: OnboardingState): OnboardingState {
  const current = normalizeOnboardingState(state);
  return {
    ...current,
    sourcesTip: "skipped"
  };
}

export function shouldAutoStartOnboarding(state: OnboardingState): boolean {
  return normalizeOnboardingState(state).tour === "unseen";
}

export function shouldRunOnboarding(
  state: OnboardingState,
  replayRequested = false
): boolean {
  return replayRequested || shouldAutoStartOnboarding(state);
}

export function shouldShowSourcesTip(state: OnboardingState): boolean {
  const current = normalizeOnboardingState(state);
  return current.tour === "completed" && current.sourcesTip === "pending";
}

function browserStorage(): OnboardingStorage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function createOnboardingStore(
  storage: OnboardingStorage | null = browserStorage()
): OnboardingStore {
  let memory = initialOnboardingState();
  let loaded = false;

  const read = () => {
    if (!loaded) {
      loaded = true;
      if (storage) {
        try {
          memory = parseOnboardingState(storage.getItem(ONBOARDING_STORAGE_KEY));
        } catch {
          // Keep the in-memory default when browser storage cannot be read.
        }
      }
    }
    return normalizeOnboardingState(memory);
  };

  const write = (state: OnboardingState) => {
    memory = normalizeOnboardingState(state);
    loaded = true;
    if (storage) {
      try {
        storage.setItem(ONBOARDING_STORAGE_KEY, serializeOnboardingState(memory));
      } catch {
        // The state remains available to this page through the in-memory copy.
      }
    }
    return normalizeOnboardingState(memory);
  };

  return { read, write };
}

let defaultStore: OnboardingStore | null = null;

function defaultOnboardingStore(): OnboardingStore {
  if (!defaultStore) defaultStore = createOnboardingStore();
  return defaultStore;
}

export function storedOnboardingState(): OnboardingState {
  return defaultOnboardingStore().read();
}

export function persistOnboardingState(state: OnboardingState): OnboardingState {
  return defaultOnboardingStore().write(state);
}
