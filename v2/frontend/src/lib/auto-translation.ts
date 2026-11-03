export type AutoTranslationRequest = { sid: string; language: string };

export function validYouTubeLink(value: string): boolean {
  try {
    const url = new URL(value);
    const host = url.hostname.replace(/^www\./, "").replace(/^m\./, "");
    const id = host === "youtu.be" ? url.pathname.slice(1) : url.searchParams.get("v") || /\/(?:shorts|live|embed)\/([^/]+)/.exec(url.pathname)?.[1];
    return ["http:", "https:"].includes(url.protocol) && ["youtube.com", "youtu.be"].includes(host) && /^[\w-]{11}$/.test(id || "");
  } catch { return false; }
}

export function autoTranslationReady(input: {
  request: AutoTranslationRequest | null;
  sessionId?: string;
  language: unknown;
  url: string;
  busy: boolean;
  running: boolean;
  healthy: boolean;
}): boolean {
  return !!input.request && input.request.sid === input.sessionId && input.request.language === input.language
    && !input.busy && !input.running && input.healthy && validYouTubeLink(input.url);
}
