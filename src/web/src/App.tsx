import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { askStream, getCorpus } from "./api";
import type { AskResponse, Corpus, ChatTurn, Mode, Source } from "./types";

const QUICK_QUESTIONS = [
  "What is the EU AI Act?",
  "How do I implement ISO 42001?",
  "What are the core functions of the NIST AI RMF?",
  "What are high-risk AI systems?",
  "GDPR requirements for AI?",
  "Compare US vs EU AI policy",
];

const STATUS_TONE: Record<string, string> = {
  in_force: "var(--ok)",
  voluntary: "var(--accent)",
  proposed: "var(--warn)",
  historical: "var(--muted)",
};

function compact(n: number): string {
  if (n < 1000) return String(n);
  return (n / 1000).toFixed(n < 10000 ? 1 : 0) + "k";
}

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }, [dark]);
  return { dark, toggle: () => setDark((d) => !d) };
}

function ThemeToggle({ dark, toggle }: { dark: boolean; toggle: () => void }) {
  return (
    <button
      onClick={toggle}
      aria-label="Toggle light or dark theme"
      title={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="hairline grid h-8 w-8 place-items-center rounded-full text-base leading-none"
      style={{ background: "var(--surface)" }}
    >
      {dark ? "☾" : "☀"}
    </button>
  );
}

function ConfidenceBadge({ value }: { value: string }) {
  const tone =
    value === "high" ? "var(--ok)" : value === "medium" ? "var(--warn)" : "var(--muted)";
  return (
    <span className="badge" style={{ color: tone, borderColor: tone }} title={`Answer confidence: ${value}`}>
      ⭐ {value} confidence
    </span>
  );
}

function CorpusExplorer({
  corpus,
  scope,
  toggleScope,
  clearScope,
}: {
  corpus: Corpus | null;
  scope: Set<string>;
  toggleScope: (j: string) => void;
  clearScope: () => void;
}) {
  const [open, setOpen] = useState(false);
  if (!corpus) return null;
  const { frameworks, documents } = corpus.stats;
  return (
    <div className="surface-card overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left text-sm"
        style={{ color: "var(--muted)" }}
      >
        <span style={{ color: "var(--ink)" }} className="font-medium">
          {frameworks} frameworks · {documents} documents
        </span>
        <span className="badge" title="dense + BM25 sparse, fused with RRF">Hybrid search</span>
        <span className="badge" title="cross-encoder bge-reranker reorders the top candidates">Reranked</span>
        <span className="badge" title="grounded answers cite their sources">Cited</span>
        <span className="ml-auto">Click to view frameworks {open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4" style={{ borderTop: "1px solid var(--line)" }}>
          <div className="flex items-center gap-2 py-3">
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              Scope:
            </span>
            {scope.size === 0 ? (
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                All frameworks
              </span>
            ) : (
              [...scope].map((j) => (
                <button key={j} className="badge" onClick={() => toggleScope(j)} style={{ color: "var(--accent)", borderColor: "var(--accent)" }}>
                  {corpus.jurisdictions[j] ?? j} ✕
                </button>
              ))
            )}
            {scope.size > 0 && (
              <button onClick={clearScope} className="ml-1 text-xs underline" style={{ color: "var(--muted)" }}>
                reset
              </button>
            )}
          </div>

          {corpus.tiers.map((tier) => (
            <details key={tier.id} className="py-1" open>
              <summary className="cursor-pointer text-sm font-medium" style={{ color: "var(--ink)" }}>
                {tier.name}{" "}
                <span className="text-xs font-normal" style={{ color: "var(--muted)" }}>
                  ({tier.documents.length})
                </span>
              </summary>
              <div className="flex flex-wrap gap-1.5 py-2">
                {tier.documents.map((d) => {
                  const active = scope.has(d.jurisdiction);
                  return (
                    <button
                      key={d.id}
                      onClick={() => toggleScope(d.jurisdiction)}
                      title={`${d.title} — click to scope to ${corpus.jurisdictions[d.jurisdiction] ?? d.jurisdiction}`}
                      className="badge"
                      style={
                        active
                          ? { color: "var(--accent)", borderColor: "var(--accent)", background: "var(--surface)" }
                          : {}
                      }
                    >
                      <span
                        className="inline-block h-1.5 w-1.5 rounded-full"
                        style={{ background: STATUS_TONE[d.status] ?? "var(--muted)" }}
                      />
                      {d.short_name}
                      <span style={{ color: "var(--muted)" }}>· {d.jurisdiction}</span>
                    </button>
                  );
                })}
              </div>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}

function SourcesPanel({ sources }: { sources: Source[] }) {
  if (!sources.length) return null;
  return (
    <details className="mt-3">
      <summary className="cursor-pointer text-sm font-medium" style={{ color: "var(--accent)" }}>
        Sources ({sources.length}) ▼
      </summary>
      <ol className="mt-2 space-y-2">
        {sources.map((s) => (
          <li key={s.position} className="surface-card p-3 text-sm" style={{ background: "var(--surface-2)" }}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">
                [{s.position}] {s.short_name}
              </span>
              {s.section_path && <span className="badge">§ {s.section_path}</span>}
              {s.page != null && <span className="badge">p.{s.page}</span>}
              <span className="badge">{s.doc_id}</span>
              {s.url && (
                <a href={s.url} target="_blank" rel="noreferrer" className="ml-auto text-xs underline" style={{ color: "var(--accent)" }}>
                  source ↗
                </a>
              )}
            </div>
            {s.quote && (
              <p className="mt-1.5 whitespace-pre-wrap text-[0.8rem]" style={{ color: "var(--muted)" }}>
                {s.quote}
              </p>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}

function MetaBar({ r }: { r: AskResponse }) {
  const t = r.token_usage;
  // Only surface an intent badge when it's meaningful to a user; the raw
  // implementation/lookup/scoping labels are internal and add noise.
  const intentLabel =
    r.intent === "comparison" ? "⇄ Comparison" : r.intent === "out_of_scope" ? "Out of scope" : null;
  // Never show a "mock" model or the "none" placeholder (list mode) to users.
  const showModel = !!r.model && r.model !== "none" && !r.model.toLowerCase().includes("mock");
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 font-mono text-[0.7rem]" style={{ color: "var(--muted)" }}>
      <ConfidenceBadge value={r.confidence} />
      {intentLabel && <span className="badge">{intentLabel}</span>}
      {showModel && <span className="badge">{r.model}</span>}
      <span className="badge" title="input / output / embedding tokens">
        ▲ {compact(t.prompt_tokens)} · ▼ {compact(t.completion_tokens)} · ⋯ {compact(t.embedding_tokens)} tok
      </span>
      {t.estimated_cost_usd > 0 && <span className="badge">${t.estimated_cost_usd.toFixed(4)}</span>}
      <span className="badge">{r.elapsed_ms} ms</span>
      <span className="badge" title="retrieval: candidates → reranked">
        {r.retrieval.candidates}→{r.retrieval.reranked} ({r.retrieval.fusion})
      </span>
      <span className="badge">{r.query_id}</span>
    </div>
  );
}

function AssistantCard({ turn }: { turn: ChatTurn }) {
  const r = turn.response;
  return (
    <div className="surface-card p-4">
      {r?.decontextualized_query && (
        <p className="mb-2 text-xs italic" style={{ color: "var(--muted)" }} title="Your follow-up was combined with the prior turn for retrieval">
          ↳ interpreted as: {r.decontextualized_query}
        </p>
      )}
      {turn.content ? (
        <div className="prose-answer text-sm">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.content}</ReactMarkdown>
          {turn.streaming && <span className="ml-0.5 inline-block animate-pulse">▍</span>}
        </div>
      ) : turn.streaming ? (
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          <span className="inline-block animate-pulse">Retrieving and composing a cited answer…</span>
        </p>
      ) : (
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          {r?.mode === "list" ? "Retrieval only (list mode) — see sources below." : "(no answer)"}
        </p>
      )}
      {r && <SourcesPanel sources={r.sources} />}
      {r && <MetaBar r={r} />}
    </div>
  );
}

export default function App() {
  const { dark, toggle } = useTheme();
  const [corpus, setCorpus] = useState<Corpus | null>(null);
  const [scope, setScope] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<Mode>("summarize");
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    getCorpus().then(setCorpus).catch((e) => setError(String(e)));
    composerRef.current?.focus({ preventScroll: true }); // ready to type on load
  }, []);

  useEffect(() => {
    // Page-level scroll: messages flow naturally; the composer sticks to the
    // viewport bottom only once the conversation overflows.
    if (turns.length) {
      window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    }
  }, [turns, loading]);

  const siteParam = useMemo(() => [...scope].join(","), [scope]);

  function toggleScope(j: string) {
    setScope((prev) => {
      const next = new Set(prev);
      next.has(j) ? next.delete(j) : next.add(j);
      return next;
    });
  }

  async function submit(q: string) {
    const query = q.trim();
    if (!query || loading) return;
    setError(null);
    setInput("");
    const prev = turns;
    const userTurn: ChatTurn = { role: "user", content: query };
    // Append the user turn + an empty assistant turn we fill as deltas stream in.
    setTurns((t) => [...t, userTurn, { role: "assistant", content: "", streaming: true }]);
    setLoading(true);
    const ac = new AbortController();
    abortRef.current = ac;

    // Patch the trailing assistant turn in place as the SSE stream progresses.
    const patchAssistant = (patch: Partial<ChatTurn>) =>
      setTurns((t) => {
        const copy = [...t];
        const i = copy.length - 1;
        if (i >= 0 && copy[i].role === "assistant") copy[i] = { ...copy[i], ...patch };
        return copy;
      });

    try {
      await askStream(
        { query, prev, site: siteParam, mode, signal: ac.signal },
        {
          onDelta: (full) => patchAssistant({ content: full }),
          onDone: (r) => patchAssistant({ content: r.answer, response: r, streaming: false }),
        },
      );
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        setError(String(e?.message ?? e));
        // drop the empty assistant placeholder on error
        setTurns((t) => (t.length && t[t.length - 1].role === "assistant" && !t[t.length - 1].response ? t.slice(0, -1) : t));
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
  }
  function clearThread() {
    setTurns([]);
    setError(null);
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-6">
      {/* Header */}
      <header className="flex items-center gap-3">
        <div className="flex-1">
          <h1 className="font-display text-2xl font-semibold tracking-tight">AI Compliance NLWeb</h1>
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            Your AI Compliance Assistant — ask questions about AI regulations and standards
          </p>
        </div>
        <ThemeToggle dark={dark} toggle={toggle} />
      </header>

      <CorpusExplorer corpus={corpus} scope={scope} toggleScope={toggleScope} clearScope={() => setScope(new Set())} />

      {/* Thread */}
      <div ref={threadRef} className="space-y-4">
        {turns.length === 0 && (
          <div className="surface-card p-6 text-center">
            <p className="font-display text-lg">Ask about AI compliance</p>
            <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
              Grounded, cited answers from {corpus?.stats.documents ?? 48} open-access frameworks. Not legal advice.
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {QUICK_QUESTIONS.map((q) => (
                <button key={q} onClick={() => submit(q)} className="hairline rounded-full px-3 py-1.5 text-sm" style={{ background: "var(--surface-2)" }}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, i) =>
          turn.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl px-4 py-2 text-sm" style={{ background: "var(--accent)", color: "var(--accent-fg)" }}>
                {turn.content}
              </div>
            </div>
          ) : (
            <AssistantCard key={i} turn={turn} />
          )
        )}

        {loading && !turns.some((t) => t.streaming) && (
          <div className="surface-card p-4 text-sm" style={{ color: "var(--muted)" }}>
            <span className="inline-block animate-pulse">Retrieving and composing a cited answer…</span>
          </div>
        )}
        {error && (
          <div className="surface-card p-3 text-sm" style={{ color: "var(--danger)", borderColor: "var(--danger)" }}>
            {error}
          </div>
        )}
      </div>

      {/* Composer + footer: sticky to the viewport bottom only when the
          conversation overflows; otherwise flows inline after the messages. */}
      <div
        className="sticky bottom-0 -mx-4 flex flex-col gap-2 px-4 pb-1 pt-2"
        style={{ background: "var(--paper)", borderTop: "1px solid var(--line)" }}
      >
      <div className="surface-card p-3">
        <div className="mb-2 flex items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
          <label htmlFor="mode-select">answer style</label>
          <select
            id="mode-select"
            value={mode}
            onChange={(e) => setMode(e.target.value as Mode)}
            title="How to answer — a cited summary, just the sources (no AI), or a drafted artifact"
            className="hairline rounded-md px-2 py-1"
            style={{ background: "var(--surface-2)", color: "var(--ink)" }}
          >
            <option value="summarize">Answer — cited summary</option>
            <option value="list">Sources only — no AI</option>
            <option value="generate">Draft — checklist / artifact</option>
          </select>
          {scope.size > 0 && <span className="badge">scope: {siteParam}</span>}
        </div>
        <textarea
          ref={composerRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(input);
            }
          }}
          rows={2}
          placeholder="Ask about AI compliance, regulations, or standards…"
          className="w-full resize-none bg-transparent text-sm outline-none"
          style={{ color: "var(--ink)" }}
        />
        <div className="mt-2 flex items-center gap-2">
          <button
            onClick={() => submit(input)}
            disabled={loading || !input.trim()}
            className="rounded-lg px-4 py-1.5 text-sm font-medium disabled:opacity-50"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          >
            Ask
          </button>
          {loading && (
            <button onClick={stop} className="hairline rounded-lg px-3 py-1.5 text-sm">
              Stop
            </button>
          )}
          <button onClick={clearThread} className="hairline rounded-lg px-3 py-1.5 text-sm" style={{ color: "var(--muted)" }}>
            Clear
          </button>
        </div>
      </div>

      {/* NLWeb showcase footer — one grounded, cited core exposed two ways */}
      <footer className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 pb-1 text-center text-xs" style={{ color: "var(--muted)" }}>
        <span>
          An <strong style={{ color: "var(--ink)" }}>NLWeb</strong> showcase:
        </span>
        <span className="badge" title="POST /ask — humans / UI: structured JSON (Schema.org ItemList)">
          <code className="font-mono">/ask</code> · humans
        </span>
        <a className="badge" href="/mcp" target="_blank" rel="noreferrer" title="GET/POST /mcp — agents: an MCP server over the same core (ask_compliance, list_frameworks, get_framework)">
          <code className="font-mono">/mcp</code> · agents ↗
        </a>
        <a className="badge" href="/docs" target="_blank" rel="noreferrer" title="Swagger UI (FastAPI OpenAPI) — also /redoc and /openapi.json">
          <code className="font-mono">/docs</code> · API ↗
        </a>
        <a
          href="https://medium.com/@dave-patten/nlweb-mcp-why-every-website-will-soon-need-an-ask-endpoint-92c8bac9d4da"
          target="_blank"
          rel="noreferrer"
          style={{ color: "var(--accent)" }}
        >
          What is NLWeb? ↗
        </a>
      </footer>
      </div>
    </div>
  );
}
