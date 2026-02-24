# C:\Users\dance\zone\kihon\kuiz\server.py
# FastAPI + Firestore クイズ API サーバー

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict
from pathlib import Path
import json
import random
import os
import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import firebase_admin
from firebase_admin import firestore, credentials


logger = logging.getLogger("quiz.app")


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Question(BaseModel):
    id: str
    category: str
    question: str
    options: List[str]
    answer: int
    explanation: Optional[str] = None


class NextQuestionResponse(BaseModel):
    question: Optional[Question]


class AnswerRequest(BaseModel):
    userId: str
    questionId: str
    choice: int
    elapsedMs: int


class AnswerResponse(BaseModel):
    correct: bool
    nextReviewAt: datetime


class StatsResponse(BaseModel):
    totalAnswers: int
    correctCount: int
    accuracy: float


class CategoryMeta(BaseModel):
    name: str
    count: int


class MetaResponse(BaseModel):
    totalQuestions: int
    categories: List[CategoryMeta]


class QuestionBatchResponse(BaseModel):
    questions: List[Question]


class SessionResultItem(BaseModel):
    questionId: str
    choice: int
    elapsedMs: int


class SessionResultsRequest(BaseModel):
    userId: str
    results: List[SessionResultItem]


class SessionResultsResponse(BaseModel):
    totalAnswers: int
    correctCount: int


_db = None
_user_index: dict[str, int] = {}


def get_db():
    global _db
    if _db is None:
        try:
            if not len(firebase_admin._apps):
                cred_path = os.getenv("QUIZ_FIRESTORE_CREDENTIALS") or os.getenv(
                    "GOOGLE_APPLICATION_CREDENTIALS"
                )
                if cred_path and Path(cred_path).exists():
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                    logger.info("Initialized Firestore with explicit credentials at %s", cred_path)
                else:
                    firebase_admin.initialize_app()
                    logger.info("Initialized Firestore with default application credentials")
            _db = firestore.client()
            logger.info("Firestore client initialized")
        except Exception as e:
            logger.warning("Error initializing Firestore: %s", e)
            _db = None
    return _db


def _load_questions_from_file() -> List[Question]:
    result: List[Question] = []
    if not DATA_DIR.exists():
        return result

    for json_file in DATA_DIR.glob("*.json"):
        if json_file.name == "firestore-schema.json":
            continue

        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue
            for i, item in enumerate(data):
                try:
                    options = item.get("options") or item.get("choices") or []
                    raw_answer = item.get("answer")

                    if isinstance(raw_answer, str):
                        try:
                            answer_idx = options.index(raw_answer)
                        except ValueError:
                            answer_idx = 0
                    else:
                        answer_idx = max(0, int(raw_answer or 0) - 1)

                    item_id = str(item.get("id") or f"{json_file.stem}_{i+1}")
                    category = item.get("category") or ("ITパスポート" if "passpo" in json_file.name else "基本情報")

                    result.append(
                        Question(
                            id=item_id,
                            category=category,
                            question=item.get("question") or "",
                            options=options,
                            answer=answer_idx,
                            explanation=item.get("explanation"),
                        )
                    )
                except Exception as e:
                    logger.warning("load_questions_from_file: skip invalid item in %s: %s", json_file.name, e)
        except Exception as e:
            logger.warning("load_questions_from_file: could not read %s: %s", json_file.name, e)

    return result


def _load_questions_from_db(db) -> List[Question]:
    try:
        docs = list(db.collection("questions").stream())
    except Exception as e:
        logger.warning("load_questions_from_db: error %s", e)
        return []
    result: List[Question] = []
    for d in docs:
        data = d.to_dict() or {}
        try:
            result.append(
                Question(
                    id=str(data.get("id") or d.id),
                    category=data.get("category") or "",
                    question=data.get("question") or "",
                    options=list(data.get("options") or []),
                    answer=int(data.get("answer", 0)),
                    explanation=data.get("explanation"),
                )
            )
        except Exception as e:
            logger.warning("load_questions_from_db: skip invalid doc %s", e)
    return result


def load_questions() -> List[Question]:
    db = get_db()
    if db is not None:
        questions = _load_questions_from_db(db)
        if questions:
            logger.info("load_questions: loaded %d questions from Firestore", len(questions))
            return questions
    questions = _load_questions_from_file()
    logger.info("load_questions: loaded %d questions from file", len(questions))
    return questions


def _update_schedule(
    repetitions: int, interval: int, ease: float, correct: bool, elapsed_ms: int
):
    if not correct:
        quality = 1
    else:
        seconds = max(0, elapsed_ms) / 1000.0
        if seconds <= 5:
            quality = 5
        elif seconds <= 12:
            quality = 4
        else:
            quality = 3
    ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    if ease < 1.3:
        ease = 1.3
    if quality < 3:
        repetitions = 0
        interval = 1
    else:
        repetitions += 1
        if repetitions == 1:
            interval = 1
        elif repetitions == 2:
            interval = 6
        else:
            interval = int(interval * ease)
    next_review = datetime.now(timezone.utc) + timedelta(days=interval)
    return repetitions, interval, ease, next_review


@app.get("/api/v1/questions/next", response_model=NextQuestionResponse)
def get_next_question(
    userId: str = Query(...),
    wrongOnly: bool = Query(False),
    avoidCorrect: bool = Query(False),
    randomMode: bool = Query(False),
):
    questions = load_questions()
    if not questions:
        return NextQuestionResponse(question=None)

    db = get_db()
    now = datetime.now(timezone.utc)

    if db is None:
        idx = _user_index.get(userId, 0)
        if idx >= len(questions):
            idx = 0
        q = questions[idx]
        _user_index[userId] = (idx + 1) % len(questions)
        return NextQuestionResponse(question=q)

    state_docs = list(
        db.collection("user_question_state").where("userId", "==", userId).stream()
    )
    state_map: Dict[str, Dict] = {}
    for doc in state_docs:
        data = doc.to_dict() or {}
        qid = data.get("questionId")
        if qid:
            state_map[qid] = data

    due: List[Question] = []
    hard: List[Question] = []
    new: List[Question] = []
    others: List[Question] = []

    for q in questions:
        s = state_map.get(q.id)
        if not s:
            new.append(q)
            continue
        repetitions = int(s.get("repetitions", 0))
        next_review = s.get("nextReviewAt")
        if isinstance(next_review, datetime) and next_review