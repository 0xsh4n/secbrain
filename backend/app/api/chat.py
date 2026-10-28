from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, require_session
from app.db import get_db
from app.models.conversation import Conversation, Message
from app.schemas.chat import (
    ChatRequest,
    ConversationCreate,
    ConversationOut,
    MessageOut,
)
from app.schemas.common import iso
from app.schemas.search import EvidenceOut
from app.services.answer import generate_answer
from app.services.llm import get_llm_provider
from app.services.retrieval import RetrievalParams, retrieve

router = APIRouter(prefix="/conversations", tags=["chat"])


def _conv_out(c: Conversation) -> ConversationOut:
    return ConversationOut(
        id=c.id,
        title=c.title,
        collection_ids=json.loads(c.collection_ids or "[]"),
        created_at=iso(c.created_at),
        updated_at=iso(c.updated_at),
    )


def _msg_out(m: Message) -> MessageOut:
    try:
        cites = [EvidenceOut(**c) for c in json.loads(m.citations or "[]")]
    except Exception:
        cites = []
    return MessageOut(id=m.id, role=m.role, content=m.content, citations=cites, created_at=iso(m.created_at))


def _get_conv(db: Session, principal: Principal, conv_id: str) -> Conversation:
    c = db.get(Conversation, conv_id)
    if c is None or c.user_id != principal.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return c


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    c = Conversation(
        organization_id=principal.user.organization_id,
        user_id=principal.user.id,
        title=payload.title,
        collection_ids=json.dumps(payload.collection_ids),
    )
    db.add(c)
    db.commit()
    return _conv_out(c)


@router.get("", response_model=list[ConversationOut])
def list_conversations(db: Session = Depends(get_db), principal: Principal = Depends(require_session)):
    rows = db.execute(
        select(Conversation)
        .where(Conversation.user_id == principal.user.id)
        .order_by(Conversation.updated_at.desc())
    ).scalars().all()
    return [_conv_out(c) for c in rows]


@router.get("/{conv_id}/messages", response_model=list[MessageOut])
def list_messages(conv_id: str, db: Session = Depends(get_db), principal: Principal = Depends(require_session)):
    c = _get_conv(db, principal, conv_id)
    return [_msg_out(m) for m in c.messages]


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conv_id: str, db: Session = Depends(get_db), principal: Principal = Depends(require_session)):
    c = _get_conv(db, principal, conv_id)
    db.delete(c)
    db.commit()


def _run_retrieval(db: Session, principal: Principal, c: Conversation, payload: ChatRequest):
    requested = payload.collection_ids or json.loads(c.collection_ids or "[]")
    params = RetrievalParams(
        query=payload.message,
        collection_ids=requested or None,
        top_k=payload.top_k,
        rerank=payload.rerank,
    )
    return retrieve(db, principal.user, params)


@router.post("/{conv_id}/messages", response_model=MessageOut)
def post_message(
    conv_id: str,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    c = _get_conv(db, principal, conv_id)
    history = [
        {"role": m.role, "content": m.content}
        for m in c.messages[-6:]
    ]
    db.add(Message(conversation_id=c.id, role="user", content=payload.message))
    evidence = _run_retrieval(db, principal, c, payload)
    result = generate_answer(payload.message, evidence, history=history)

    if not result.model_available:
        # Persist the user message; surface a clear model-unavailable error.
        db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Generation model unavailable: {result.model_error}",
        )

    citations = json.dumps([e.to_dict() for e in result.evidence])
    assistant = Message(
        conversation_id=c.id, role="assistant", content=result.answer, citations=citations
    )
    db.add(assistant)
    db.add(c)
    db.commit()
    return _msg_out(assistant)


@router.post("/{conv_id}/stream")
def stream_message(
    conv_id: str,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_session),
):
    """Server-sent-events style stream: evidence first, then answer tokens."""
    c = _get_conv(db, principal, conv_id)
    history = [
        {"role": m.role, "content": m.content}
        for m in c.messages[-6:]
    ]
    db.add(Message(conversation_id=c.id, role="user", content=payload.message))
    db.commit()
    evidence = _run_retrieval(db, principal, c, payload)
    message = payload.message

    def event_gen():
        yield "event: evidence\ndata: " + json.dumps([e.to_dict() for e in evidence]) + "\n\n"
        if not evidence:
            res = generate_answer(message, evidence, history=history)
            yield "event: token\ndata: " + json.dumps({"text": res.answer}) + "\n\n"
            _persist_assistant(conv_id, res.answer, evidence)
            yield "event: done\ndata: {}\n\n"
            return
        provider = get_llm_provider()
        from app.services.answer import _SYSTEM_PROMPT, _build_evidence_block

        history_block = ""
        if history:
            turns = [
                f"{('User' if h.get('role') == 'user' else 'Assistant')}: {h.get('content', '').strip()}"
                for h in history
            ]
            history_block = "PRIOR CONVERSATION CONTEXT:\n" + "\n".join(turns) + "\n\n"

        user_prompt = (
            f"{history_block}CURRENT QUESTION: {message}\n\n{_build_evidence_block(evidence)}\n\n"
            "Answer grounded in the evidence, citing labels like [E1]."
        )
        collected: list[str] = []
        try:
            for piece in provider.stream(_SYSTEM_PROMPT, user_prompt):
                collected.append(piece)
                yield "event: token\ndata: " + json.dumps({"text": piece}) + "\n\n"
        except Exception as exc:
            yield "event: error\ndata: " + json.dumps({"detail": str(exc)}) + "\n\n"
            return
        _persist_assistant(conv_id, "".join(collected), evidence)
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def _persist_assistant(conv_id: str, content: str, evidence) -> None:
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        db.add(
            Message(
                conversation_id=conv_id,
                role="assistant",
                content=content,
                citations=json.dumps([e.to_dict() for e in evidence]),
            )
        )
        db.commit()
    finally:
        db.close()
