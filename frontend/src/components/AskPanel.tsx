"use client";

import { useState } from "react";
import Link from "next/link";
import {
  askQuestion,
  ApiError,
  type AskResponse,
  type Citation,
} from "@/lib/api";
import {
  INTENT_LABELS,
  INTENT_EXPLANATIONS,
  intentTone,
  isSimulated,
  metricKeyLabel,
} from "@/lib/format";

function CitationChip({ citation }: { citation: Citation }) {
  const simulated = isSimulated(citation.provenance);
  const metrics = citation.metric_keys
    .slice(0, 3)
    .map(metricKeyLabel)
    .join(", ");
  const overflow = citation.metric_keys.length - 3;

  const label = citation.location_name
    ? citation.location_name
    : citation.chunk_id.startsWith("meth:")
      ? "Methodology"
      : "Reference";

  const body = (
    <>
      <span className="font-medium text-ink">{label}</span>
      {metrics && (
        <span className="text-ink-faint">
          {" "}
          {metrics}
          {overflow > 0 ? ` +${overflow}` : ""}
        </span>
      )}
      {simulated && (
        <span className="ml-1 bg-flag-soft px-1 text-[10px] font-medium text-flag">
          sim
        </span>
      )}
    </>
  );

  if (citation.fips) {
    return (
      <Link
        href={`/report/${citation.fips}`}
        className="border border-rule bg-surface px-2.5 py-1 text-xs transition-colors hover:border-accent"
      >
        {body}
      </Link>
    );
  }

  const href = citation.source_urls[0];
  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="border border-rule bg-surface px-2.5 py-1 text-xs transition-colors hover:border-accent"
      >
        {body}
      </a>
    );
  }

  return (
    <span className="border border-rule bg-surface px-2.5 py-1 text-xs">
      {body}
    </span>
  );
}

export default function AskPanel({ locationName }: { locationName?: string }) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTrace, setShowTrace] = useState(false);

  const suggestions = locationName
    ? [
        `Why is the growth score what it is in ${locationName}?`,
        `What is the median rent in ${locationName}?`,
        "How is the Growth Score calculated?",
      ]
    : [
        "Compare Hoboken and Camden",
        "Why is employment reported at the county level?",
        "How is the Growth Score calculated?",
      ];

  async function submit(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError(null);
    setResult(null);
    setShowTrace(false);

    try {
      setResult(await askQuestion(trimmed));
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        setError(
          "The assistant index hasn't been built yet. Run `python -m ingestion.build_index` in the backend folder.",
        );
      } else if (e instanceof ApiError) {
        setError(e.message);
      } else {
        setError(
          "Can't reach the CivicLens API. Make sure the backend is running on port 8000.",
        );
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="border border-rule bg-surface p-6">
      <h2 className="serif text-lg text-ink">Ask about this data</h2>
      <p className="mt-1 text-sm text-ink-muted">
        Figures come from a database query. Explanations come from indexed
        records.
      </p>

      <div className="mt-4 flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit(question)}
          placeholder="Ask about a municipality"
          className="w-full border border-rule-strong bg-surface px-4 py-3 text-sm text-ink outline-none transition-colors placeholder:text-ink-faint focus:border-accent"
        />
        <button
          onClick={() => submit(question)}
          disabled={loading || !question.trim()}
          className="shrink-0 bg-accent px-5 py-3 text-sm font-medium text-white transition-colors hover:opacity-90 disabled:bg-rule disabled:text-ink-faint"
        >
          {loading ? "Asking..." : "Ask"}
        </button>
      </div>

      {!result && !error && !loading && (
        <div className="mt-3 flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => {
                setQuestion(s);
                submit(s);
              }}
              className="border border-rule px-3 py-1.5 text-xs text-ink-muted transition-colors hover:border-accent hover:text-accent"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div className="mt-4 border-l-2 border-unfavourable bg-surface px-4 py-3 text-sm text-ink">
          {error}
        </div>
      )}

      {result && !result.grounded && (
        <div className="mt-4 border-l-2 border-flag bg-flag-soft px-4 py-3">
          <p className="text-sm text-ink">{result.answer}</p>
          {result.suggestions?.length > 0 && (
            <div className="mt-3">
              <p className="text-xs text-ink-muted">Try instead</p>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {result.suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      setQuestion(s);
                      submit(s);
                    }}
                    className="border border-rule bg-surface px-2.5 py-1 text-xs text-ink-muted transition-colors hover:border-accent hover:text-accent"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {result && result.grounded && (
        <div className="mt-4">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`border px-2.5 py-0.5 text-xs font-medium ${intentTone(result.intent)}`}
            >
              {INTENT_LABELS[result.intent] ?? result.intent}
            </span>
            {result.provenance === "simulated" && (
              <span className="border border-flag/40 bg-flag-soft px-2.5 py-0.5 text-xs font-medium text-flag">
                Demonstration data
              </span>
            )}
          </div>

          <p className="mt-3 whitespace-pre-line leading-relaxed text-ink">
            {result.answer}
          </p>

          <p className="mt-3 border-l-2 border-rule pl-3 text-xs leading-relaxed text-ink-muted">
            {INTENT_EXPLANATIONS[result.intent]}
          </p>

          {result.citations.length > 0 && (
            <div className="mt-4 border-t border-rule pt-3">
              <div className="text-xs text-ink-faint">Sources</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {result.citations.map((c) => (
                  <CitationChip key={c.chunk_id} citation={c} />
                ))}
              </div>
            </div>
          )}

          <button
            onClick={() => setShowTrace(!showTrace)}
            className="mt-3 text-xs text-ink-faint underline underline-offset-4 transition-colors hover:text-ink"
          >
            {showTrace ? "Hide retrieval trace" : "Show retrieval trace"}
          </button>

          {showTrace && (
            <div className="mt-2 border border-rule bg-paper p-3 text-xs text-ink-muted">
              <div>
                Retrieval:{" "}
                {result.retrieval.used
                  ? `${result.retrieval.chunks.length} chunks, top score ${result.retrieval.top_score}`
                  : "not used, answered by direct query"}
              </div>
              {result.retrieval.generator && (
                <div className="mt-1">
                  Generator: {result.retrieval.generator}
                </div>
              )}
              {result.resolved_places.length > 0 && (
                <div className="mt-1">
                  Resolved:{" "}
                  {result.resolved_places
                    .map((p) => `${p.name} (${p.fips})`)
                    .join(", ")}
                </div>
              )}
              <div className="tabular mt-1 break-words text-[11px] text-ink-faint">
                {result.citations.map((c) => c.chunk_id).join("  ")}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
