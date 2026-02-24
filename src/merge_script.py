import json
from pathlib import Path

data_dir = Path(r"i:\My Drive\KUIZ\kihon\data")
questions_path = data_dir / "questions.json"
q2_path = data_dir / "q2.json"
output_path = data_dir / "kihon.json"

with open(questions_path, "r", encoding="utf-8") as f:
    questions = json.load(f)

with open(q2_path, "r", encoding="utf-8") as f:
    q2 = json.load(f)

merged = questions.copy()
next_id = max(q["id"] for q in questions) + 1 if questions else 1

for item in q2:
    choices = item.get("choices", [])
    answer_text = item.get("answer", "")
    
    # Find index (1-based)
    try:
        answer_idx = choices.index(answer_text) + 1
    except ValueError:
        print(f"Warning: Answer '{answer_text}' not found in choices for question: {item.get('question')[:20]}...")
        answer_idx = 1 # Default
    
    merged.append({
        "id": next_id,
        "category": item.get("category", "基本情報"),
        "question": item.get("question"),
        "options": choices,
        "answer": answer_idx,
        "explanation": item.get("explanation", None)
    })
    next_id += 1

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)

print(f"Successfully merged {len(merged)} questions into kihon.json")
