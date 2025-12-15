// apps/mobile/src/api.ts

import { Consent } from "./state";

type Auth = {
  sessionId: string;
  accessToken?: string | null;
  deviceToken: string;
};

function authHeaders(auth: Auth) {
  const h: any = { "X-Device-Token": auth.deviceToken };
  if (auth.accessToken) h["Authorization"] = `Bearer ${auth.accessToken}`;
  return h;
}

export async function createSession(apiBaseUrl: string, deviceToken: string) {
  const r = await fetch(`${apiBaseUrl}/v1/session`, {
    method: "POST",
    headers: { "X-Device-Token": deviceToken },
  });
  if (!r.ok) throw new Error("Failed to create session");
  return r.json() as Promise<{ session_id: string; access_token?: string | null }>;
}

export async function upsertConsent(apiBaseUrl: string, auth: Auth, consent: Consent) {
  const r = await fetch(`${apiBaseUrl}/v1/consent?session_id=${encodeURIComponent(auth.sessionId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(auth) },
    body: JSON.stringify(consent),
  });
  if (!r.ok) throw new Error("Failed to save consent");
}

export async function analyze(apiBaseUrl: string, auth: Auth, jpegUri: string) {
  const form = new FormData();
  form.append("image", {
    uri: jpegUri,
    name: "photo.jpg",
    type: "image/jpeg",
  } as any);

  const r = await fetch(`${apiBaseUrl}/v1/analyze?session_id=${encodeURIComponent(auth.sessionId)}`, {
    method: "POST",
    headers: authHeaders(auth),
    body: form,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function labelSample(
  apiBaseUrl: string,
  auth: Auth,
  payload: {
    roi_sha256: string;
    labels: Record<string, number>;
    fitzpatrick?: "I" | "II" | "III" | "IV" | "V" | "VI";
    age_band?: "<18" | "18-24" | "25-34" | "35-44" | "45-54" | "55-64" | "65+";
  }
) {
  const r = await fetch(`${apiBaseUrl}/v1/label?session_id=${encodeURIComponent(auth.sessionId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(auth) },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
