from __future__ import annotations

import json
import hashlib
import re

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
from app.services.retrieval import Evidence, RetrievalParams, retrieve
from app.services.web_search import search_web
from app.config import settings

router = APIRouter(prefix="/conversations", tags=["chat"])
_OUTPUT_TOKENS = {"balanced": 1024, "detailed": 2048, "extended": 4096}


def _answer_budget(payload: ChatRequest) -> int:
    return min(_OUTPUT_TOKENS[payload.response_length], settings.llm_max_output_tokens)


def _web_evidence(query: str) -> list[Evidence]:
    try:
        results = search_web(query)
    except Exception:
        return []
    return [
        Evidence(
            document_id="",
            chunk_id=f"web-{index}-{hashlib.sha256(result.url.encode()).hexdigest()[:12]}",
            title=result.title,
            source_url=result.url,
            source_type="web",
            text=result.snippet,
            page_number=None,
            section_heading="",
            retrieval_method="web search",
            score=1.0,
            collection_ids=[],
        )
        for index, result in enumerate(results, start=1)
    ]


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


_CONVERSATIONAL_WORDS = {
    "hi", "hello", "hey", "sup", "yo", "thanks", "thank", "thank you",
    "how are you", "who are you", "good morning", "good evening", "good afternoon",
    "what's up", "whats up", "ok", "okay", "bye", "goodbye"
}

def _is_conversational(text: str) -> bool:
    clean = re.sub(r"[^\w\s]", "", text.strip().lower()).strip()
    if clean in _CONVERSATIONAL_WORDS:
        return True
    words = clean.split()
    if len(words) <= 4 and any(w in {"hi", "hello", "hey", "sup", "greetings"} for w in words):
        security_keywords = {"cve", "cwe", "vuln", "vulnerability", "exploit", "audit", "security", "scan", "token", "password", "port"}
        if not any(k in words for k in security_keywords):
            return True
    return False

def _run_retrieval(db: Session, principal: Principal, c: Conversation, payload: ChatRequest):
    if _is_conversational(payload.message):
        return []
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
    history_rows = db.execute(
        select(Message).where(Message.conversation_id == c.id)
        .order_by(Message.created_at.desc()).limit(6)
    ).scalars().all()
    history = [{"role": m.role, "content": m.content} for m in reversed(history_rows)]
    db.add(Message(conversation_id=c.id, role="user", content=payload.message))
    evidence = _run_retrieval(db, principal, c, payload)
    if payload.web_search:
        evidence.extend(_web_evidence(payload.message))
    result = generate_answer(payload.message, evidence, history=history, max_output_tokens=_answer_budget(payload), thinking=payload.thinking)

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
    history_rows = db.execute(
        select(Message).where(Message.conversation_id == c.id)
        .order_by(Message.created_at.desc()).limit(6)
    ).scalars().all()
    history = [{"role": m.role, "content": m.content} for m in reversed(history_rows)]
    db.add(Message(conversation_id=c.id, role="user", content=payload.message))
    db.commit()
    evidence = _run_retrieval(db, principal, c, payload)
    message = payload.message
    conversation_id = c.id
    # Do not hold a database connection open while a long model stream runs.
    db.close()

    def event_gen():
        stream_evidence = list(evidence)
        if payload.web_search:
            yield "event: status\ndata: " + json.dumps({"text": "Searching the web…"}) + "\n\n"
            web_items = _web_evidence(message)
            stream_evidence.extend(web_items)
            if not web_items:
                yield "event: notice\ndata: " + json.dumps({"text": "Web search returned no results; answering from your knowledge pool and model knowledge."}) + "\n\n"
        provider = get_llm_provider()
        from app.services.answer import _SYSTEM_PROMPT, _build_evidence_block

        history_block = ""
        if history:
            turns = [
                f"{('User' if h.get('role') == 'user' else 'Assistant')}: {h.get('content', '').strip()}"
                for h in history
            ]
            history_block = "PRIOR CONVERSATION CONTEXT:\n" + "\n".join(turns) + "\n\n"

        if stream_evidence:
            evidence_section = (
                f"{_build_evidence_block(stream_evidence)}\n\n"
                "Answer using the evidence above as background context. Do not print evidence labels or quote large passages. "
                "If code or scripts are requested, provide clean, complete implementations."
            )
        else:
            evidence_section = (
                "Note: No specific documents were retrieved from the knowledge base for this query. "
                "Answer using your expert cybersecurity domain knowledge. Provide complete code, scripts, or methodologies as requested."
            )

        user_prompt = f"{history_block}CURRENT QUESTION: {message}\n\n{evidence_section}"
        length_guidance = {
            "balanced": "Use a compact answer, but still answer every numbered item.",
            "detailed": "Give a detailed answer while keeping each sub-answer focused.",
            "extended": "Use the full response budget. First count every requested question or list item, preserve their order and numbering, and answer each one. For 10 or more items, keep each answer concise enough to complete the entire list. Do not omit later items for a long introduction.",
        }[payload.response_length]
        user_prompt += f"\n\nRESPONSE INSTRUCTIONS: {length_guidance}"
        if payload.thinking:
            user_prompt += " Carefully verify assumptions and reason through the requested parts before answering. Provide conclusions and a brief rationale, but do not reveal private chain-of-thought."
        collected: list[str] = []
        try:
            for piece in provider.stream(_SYSTEM_PROMPT, user_prompt, max_output_tokens=_answer_budget(payload), thinking=payload.thinking):
                collected.append(piece)
                yield "event: token\ndata: " + json.dumps({"text": piece}) + "\n\n"
        except Exception as exc:
            yield "event: error\ndata: " + json.dumps({"detail": str(exc)}) + "\n\n"
            return
        _persist_assistant(conversation_id, "".join(collected), stream_evidence)
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
