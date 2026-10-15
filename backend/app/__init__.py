"""Retrieval-augmented question answering over the CivicLens dataset.

The design problem
------------------
The underlying data is numeric time series, not prose. Embedding rows of
figures and retrieving them by similarity works badly: fact cards for
neighbouring municipalities are nearly identical in shape, so a question
about Montclair happily returns Bloomfield's card. And a language model
handed a table of numbers will produce a fluent, confident, wrong figure.

So the module is built around one constraint: values come from SQL, and
any number in generated prose must appear in the records it was written
from.

Request flow
------------
    question
       |
    resolver.py      municipality names -> FIPS codes
       |
    query_router.py  classify intent
       |
       +-- LOOKUP ------> SQL -> format string      (no model)
       +-- COMPARE -----> SQL -> format string      (no model; a "why"
       |                  comparison adds a checked retrieved explanation)
       +-- EXPLANATORY -> retrieve -> model -> numeric check
       +-- METHODOLOGY -> retrieve -> model -> numeric check
       +-- UNSUPPORTED -> refuse, with suggestions

Questions asking for a value are answered by a database query. Only
questions asking *why* reach a model, and then only with retrieved text in
the prompt. The model's answer is then checked number by number against that
text (numeric_check.py); an answer with a figure the records do not contain
is discarded for the extractive one. Fabricated figures are blocked in code
rather than discouraged by prompt instructions.

The cost is that intent classification becomes a correctness boundary: a
misrouted lookup lands in the model. That is why routing is rule-based and
covered by parametrised tests rather than being a second model call.

Modules
-------
corpus.py       Builds what is retrievable. Fact cards are generated from
                the metrics table, so they cannot drift from what the API
                serves. Methodology documents are hand-written and are what
                let the assistant explain a data limitation instead of
                inventing a reason for it.

embeddings.py   Provider interface. Production uses a hosted embedding API;
                Render's 512MB tier cannot host a local model. The offline
                hashing embedder makes the pipeline runnable, and the eval
                suite reproducible, with no network and no API keys.

lexical.py      BM25. Dense vectors handle paraphrase and miss exact tokens;
                BM25 is the reverse. Both run and their rankings are fused.

store.py        Chunk persistence and hybrid retrieval. Vectors live in the
                same database as the metrics they describe, so there is no
                second datastore to fall out of sync on a data refresh.

llm.py          Generation providers, plus an extractive fallback that
                selects sentences from retrieved text. The fallback cannot
                state anything that was not retrieved.

numeric_check.py  Post-generation check that every number in a generated
                answer appears in its retrieved context.

answer.py       Orchestration, guardrails, citations, refusals.

Every response carries the retrieved chunk ids, the resolved FIPS codes and
the provenance of the underlying observations, so any answer can be traced
back to the records that produced it. Retrieval quality is measured by a
labelled eval set in tests/test_retrieval_eval.py, because relevance
regresses silently: nothing throws an exception when answers quietly get
worse.
"""
