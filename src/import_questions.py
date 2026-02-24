# C:\Users\dance\zone\kihon\kuiz\import_questions.py
import os
import json
from pathlib import Path
import firebase_admin
from firebase_admin import credentials, firestore

# サービスアカウントキーのパス
project_root = Path(__file__).parent.parent
key_file = project_root / ".key" / "kuiz-ebfe2-c3bc78e92553.json"

# Firebase 初期化
if not len(firebase_admin._apps):
    if key_file.exists():
        cred = credentials.Certificate(str(key_file))
        firebase_admin.initialize_app(cred)
        print(f"Using key file: {key_file}")
    else:
        print("Key file not found, trying default credentials")
        firebase_admin.initialize_app()

db = firestore.client()

# data 読み込み
data_dir = Path(__file__).parent.parent / "data"
all_questions = []

for json_file in data_dir.glob("*.json"):
    if json_file.name == "firestore-schema.json":
        continue
    
    try:
        data = json.loads(json_file.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        for i, item in enumerate(data):
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
            
            all_questions.append({
                "id": item_id,
                "category": category,
                "question": item.get("question") or "",
                "options": options,
                "answer": answer_idx,
                "explanation": item.get("explanation")
            })
    except Exception as e:
        print(f"Error reading {json_file}: {e}")

# 既存 questions クリア＆新規追加
batch = db.batch()
coll = db.collection("questions")

# 既存ドキュメントを削除
for doc in coll.stream():
    batch.delete(doc.reference)

# 新しい問題を追加
for q in all_questions:
    doc_id = q["id"]
    batch.set(coll.document(doc_id), q)

batch.commit()
print(f"Imported {len(all_questions)} questions to Firestore")