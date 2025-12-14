import { Consent } from "./state";

export async function createSession(apiBaseUrl: string) {
  const r = await fetch(`${apiBaseUrl}/v1/session`, { method: "POST" });
  if (!r.ok) throw new Error("Failed to create session");
  return r.json() as Promise<{ session_id: string }>;
}

export async function upsertConsent(apiBaseUrl: string, sessionId: string, consent: Consent) {
  const r = await fetch(`${apiBaseUrl}/v1/consent?session_id=${encodeURIComponent(sessionId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(consent),
  });
  if (!r.ok) throw new Error("Failed to save consent");
}

export async function analyze(apiBaseUrl: string, sessionId: string, jpegUri: string) {
  const form = new FormData();
  form.append("image", {
    uri: jpegUri,
    name: "roi.jpg",
    type: "image/jpeg",
  } as any);

  const r = await fetch(`${apiBaseUrl}/v1/analyze?session_id=${encodeURIComponent(sessionId)}`, {
    method: "POST",
    body: form,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function deleteProgress(apiBaseUrl: string, sessionId: string) {
  const r = await fetch(`${apiBaseUrl}/v1/progress/delete_all?session_id=${encodeURIComponent(sessionId)}`, {
    method: "POST",
  });
  if (!r.ok) throw new Error("Failed to delete progress");
}
