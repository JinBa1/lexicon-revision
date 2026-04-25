export type ClerkTestState = {
  isLoaded: boolean;
  isSignedIn: boolean;
  token: string | null;
};

const defaultState: ClerkTestState = {
  isLoaded: true,
  isSignedIn: false,
  token: null,
};

let currentState: ClerkTestState = { ...defaultState };

export function getClerkTestState() {
  return currentState;
}

export function setClerkTestState(next: Partial<ClerkTestState>) {
  currentState = { ...currentState, ...next };
}

export function resetClerkTestState() {
  currentState = { ...defaultState };
}
