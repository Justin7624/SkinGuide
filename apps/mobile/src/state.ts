export type Consent = {
  store_progress_images: boolean;
  donate_for_improvement: boolean;
};

export type AppState = {
  apiBaseUrl: string;
  sessionId: string | null;
  consent: Consent;
};

export const defaultState: AppState = {
  apiBaseUrl: "http://localhost:8000", // change to your deployed API
  sessionId: null,
  consent: { store_progress_images: false, donate_for_improvement: false }
};
