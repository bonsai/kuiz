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
        if isinstance(next_review, datetime) and next_review <= now:
            due.append(q)
        elif repetitions == 0:
            hard.append(q)
        else:
            others.append(q)

    candidates: List[Question] = []

    if wrongOnly:
        candidates = hard or due or new or others
    elif due:
        candidates = due
    elif avoidCorrect:
        candidates = hard or new or others or due
    else:
        candidates = new or due or others or hard

    if not candidates:
        return NextQuestionResponse(question=None)

    if randomMode or wrongOnly or avoidCorrect:
        q = random.choice(candidates)
    else:
        q = candidates[0]

    return NextQuestionResponse(question=q)


@app.get("/api/v1/questions", response_model=list[Question])
def list_questions():
    return load_questions()


@app.get("/api/v1/meta", response_model=MetaResponse)
def get_meta():
    questions = load_questions()
    total = len(questions)
    by_cat: Dict[str, int] = {}
    for q in questions:
        by_cat[q.category] = by_cat.get(q.category, 0) + 1
    categories = [
        CategoryMeta(name=name, count=count) for name, count in sorted(by_cat.items())
    ]
    response = MetaResponse(totalQuestions=total, categories=categories)
    logger.info("Meta requested: total_questions=%d, categories=%d", total, len(categories))
    return response


@app.get("/api/v1/questions/batch", response_model=QuestionBatchResponse)
def get_questions_batch(
    userId: str = Query(...),
    limit: int = Query(30, ge=1, le=100),
    wrongOnly: bool = Query(False),
    avoidCorrect: bool = Query(False),
    randomMode: bool = Query(True),
):
    questions = load_questions()
    if not questions:
        logger.warning("questions_batch requested but no questions available")
        return QuestionBatchResponse(questions=[])

    db = get_db()
    now = datetime.now(timezone.utc)

    if db is None:
        if randomMode or wrongOnly or avoidCorrect:
            if limit >= len(questions):
                selected = questions[:]
                random.shuffle(selected)
            else:
                selected = random.sample(questions, limit)
        else:
            selected = questions[:limit]
        logger.info(
            "questions_batch without Firestore: userId=%s limit=%d selected=%d",
            userId,
            limit,
            len(selected),
        )
        return QuestionBatchResponse(questions=selected)

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
        if isinstance(next_review, datetime) and next_review <= now:
            due.append(q)
        elif repetitions == 0:
            hard.append(q)
        else:
            others.append(q)

    selected: List[Question] = []

    while len(selected) < limit and (due or hard or new or others):
        if wrongOnly:
            pool = hard or due or new or others
        elif due:
            pool = due
        elif avoidCorrect:
            pool = hard or new or others or due
        else:
            pool = new or due or others or hard

        if not pool:
            break

        if randomMode or wrongOnly or avoidCorrect:
            q = random.choice(pool)
        else:
            q = pool[0]

        selected.append(q)
        if q in hard:
            hard.remove(q)
        elif q in due:
            due.remove(q)
        elif q in new:
            new.remove(q)
        elif q in others:
            others.remove(q)

    logger.info(
        "questions_batch with Firestore: userId=%s limit=%d selected=%d due=%d hard=%d new=%d others=%d",
        userId,
        limit,
        len(selected),
        len(due),
        len(hard),
        len(new),
        len(others),
    )
    return QuestionBatchResponse(questions=selected)


@app.post("/api/v1/answers", response_model=AnswerResponse)
def submit_answer(payload: AnswerRequest):
    questions = load_questions()
    q = next((x for x in questions if x.id == payload.questionId), None)
    if q is None:
        logger.warning(
            "submit_answer: question not found userId=%s questionId=%s",
            payload.userId,
            payload.questionId,
        )
        raise HTTPException(status_code=404, detail="question not found")
    correct = q.answer == payload.choice

    db = get_db()
    repetitions = 0
    interval = 1
    ease = 2.5
    if db is not None:
        state_ref = db.collection("user_question_state").document(
            f"{payload.userId}_{payload.questionId}"
        )
        state_doc = state_ref.get()
        if state_doc.exists:
            state = state_doc.to_dict() or {}
            repetitions = int(state.get("repetitions", 0))
            interval = int(state.get("interval", 1))
            ease = float(state.get("ease", 2.5))
    repetitions, interval, ease, next_review = _update_schedule(
        repetitions, interval, ease, correct, payload.elapsedMs
    )
    if db is not None:
        state_ref = db.collection("user_question_state").document(
            f"{payload.userId}_{payload.questionId}"
        )
        state_ref.set(
            {
                "userId": payload.userId,
                "questionId": payload.questionId,
                "repetitions": repetitions,
                "interval": interval,
                "ease": ease,
                "nextReviewAt": next_review,
                "updatedAt": datetime.now(timezone.utc),
            },
            merge=True,
        )
        answers_ref = db.collection("answers")
        answers_ref.add(
            {
                "userId": payload.userId,
                "questionId": payload.questionId,
                "choice": payload.choice,
                "correct": correct,
                "elapsedMs": payload.elapsedMs,
                "createdAt": datetime.now(timezone.utc),
            }
        )
        stats_ref = db.collection("user_stats").document(payload.userId)
        stats_doc = stats_ref.get()
        total_answers = 0
        correct_count = 0
        total_elapsed = 0
        if stats_doc.exists:
            stats = stats_doc.to_dict() or {}
            total_answers = int(stats.get("totalAnswers", 0))
            correct_count = int(stats.get("correctCount", 0))
            total_elapsed = int(stats.get("totalElapsedMs", 0))
        total_answers += 1
        if correct:
            correct_count += 1
        total_elapsed += max(0, int(payload.elapsedMs))
        accuracy = correct_count / total_answers if total_answers > 0 else 0.0
        stats_ref.set(
            {
                "userId": payload.userId,
                "totalAnswers": total_answers,
                "correctCount": correct_count,
                "totalElapsedMs": total_elapsed,
                "accuracy": accuracy,
                "lastAnsweredAt": datetime.now(timezone.utc),
            },
            merge=True,
        )
    logger.info(
        "submit_answer: userId=%s questionId=%s correct=%s elapsedMs=%d",
        payload.userId,
        payload.questionId,
        correct,
        payload.elapsedMs,
    )
    return AnswerResponse(correct=correct, nextReviewAt=next_review)


@app.post("/api/v1/session/results", response_model=SessionResultsResponse)
def submit_session_results(payload: SessionResultsRequest):
    total = 0
    correct = 0
    for item in payload.results:
        answer_payload = AnswerRequest(
            userId=payload.userId,
            questionId=item.questionId,
            choice=item.choice,
            elapsedMs=item.elapsedMs,
        )
        resp = submit_answer(answer_payload)
        total += 1
        if resp.correct:
            correct += 1
    logger.info(
        "session_results: userId=%s total=%d correct=%d",
        payload.userId,
        total,
        correct,
    )
    return SessionResultsResponse(totalAnswers=total, correctCount=correct)


@app.get("/api/v1/stats", response_model=StatsResponse)
def get_stats(userId: str = Query(...)):
    db = get_db()
    if db is None:
        logger.info("stats requested without Firestore: userId=%s", userId)
        return StatsResponse(totalAnswers=0, correctCount=0, accuracy=0.0)
    stats_ref = db.collection("user_stats").document(userId)
    stats_doc = stats_ref.get()
    if stats_doc.exists:
        data = stats_doc.to_dict() or {}
        total = int(data.get("totalAnswers", 0))
        correct = int(data.get("correctCount", 0))
        accuracy = float(data.get("accuracy", 0.0))
        logger.info(
            "stats requested from user_stats: userId=%s total=%d correct=%d accuracy=%.4f",
            userId,
            total,
            correct,
            accuracy,
        )
        return StatsResponse(totalAnswers=total, correctCount=correct, accuracy=accuracy)
    docs = list(db.collection("answers").where("userId", "==", userId).stream())
    total = len(docs)
    if total == 0:
        logger.info("stats requested: userId=%s total=0", userId)
        return StatsResponse(totalAnswers=0, correctCount=0, accuracy=0.0)
    correct = sum(1 for d in docs if (d.to_dict() or {}).get("correct"))
    accuracy = correct / total
    logger.info(
        "stats requested from answers: userId=%s total=%d correct=%d accuracy=%.4f",
        userId,
        total,
        correct,
        accuracy,
    )
    return StatsResponse(totalAnswers=total, correctCount=correct, accuracy=accuracy)


@app.get("/health")
def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

