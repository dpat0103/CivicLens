"""Natural-language question endpoint.

Thin by design. All routing, retrieval and guardrail logic lives in
app.rag.answer so it can be tested without an HTTP layer; this module only
handles transport concerns.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..rag import store
from ..rag.answer import answer_question
from ..schemas import AskRequest, AskResponse, CorpusStats

router = APIRouter(prefix="/ask", tags=["assistant"])


@router.post("", response_model=AskResponse)
def ask(payload: AskRequest, db: Session = Depends(get_db)):
    """Answer a question about New Jersey municipal statistics.

    The response always reports which path produced it. `intent` of lookup
    or compare means the figures came from SQL with no model involved;
    explanatory or methodology means a model wrote the answer from the
    retrieved records listed in `citations`. Clients are expected to show
    that distinction, because the two carry different confidence.

    Returns 503 rather than an empty answer when the index has not been
    built, since that is an operator error with a specific fix.
    """
    if store.corpus_stats(db)["total_chunks"] == 0:
        raise HTTPException(
            status_code=503,
            detail="The assistant index is empty. Run `python -m ingestion.build_index` first.",
        )
    return answer_question(db, payload.question)


@router.get("/corpus", response_model=CorpusStats, tags=["assistant"])
def corpus(db: Session = Depends(get_db)):
    """Index size and active embedding provider.

    Useful for confirming a deployment actually ran build_index, which is
    otherwise invisible: the API stays up and answers degrade silently.
    """
    return store.corpus_stats(db)