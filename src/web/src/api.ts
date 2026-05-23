import type { AskResponse, Corpus, ChatTurn, Mode, Source } from "./types";

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return (await res.json()) as T;
}

export async function getCorpus(): Promise<Corpus> {
  return jsonOrThrow<Corpus>(await fetch("/corpus"));
}

export interface AskArgs {
  query: string;
  prev: ChatTurn[];
  site?: string;
  mode: Mode;
  signal?: AbortSignal;
}

function askBody({ query, prev, site, mode }: AskArgs) {
  return JSON.stringify({
    query,
    mode,
    site: site || undefined,
    prev: prev.map((t) => ({ role: t.role, content: t.content })),
  });
}

export async function ask(args: AskArgs): Promise<AskResponse> {
  const res = await fetch("/ask", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: askBody(args),
    signal: args.signal,
  });
  return jsonOrThrow<AskResponse>(res);
}

export interface AskStreamHandlers {
  onSources?: (sources: Source[]) => void;
  onDelta: (full: string) => void; // full answer so far
  onDone: (resp: AskResponse) => void;
}

/** POST /ask/stream — consume the SSE sequence (sources → delta → done). */
export async function askStream(args: AskArgs, h: AskStreamHandlers): Promise<void> {
  const res = await fetch("/ask/stream", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: askBody(args),
    signal: args.signal,
  });
  if (!res.ok || !res.body) {
    await jsonOrThrow<unknown>(res); // surfaces the FastAPI error detail
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let full = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      let event = "";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data = line.slice(5).trim();
      }
      if (!event || !data) continue;
      if (event === "sources") h.onSources?.(JSON.parse(data) as Source[]);
      else if (event === "delta") {
        full += (JSON.parse(data) as { text: string }).text;
        h.onDelta(full);
      } else if (event === "done") h.onDone(JSON.parse(data) as AskResponse);
    }
  }
}
