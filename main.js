const userId = "demo-user";
const API_BASE = "";

const questionEl = document.getElementById("question");
const optionsEl = document.getElementById("options");
const feedbackEl = document.getElementById("feedback");
const nextBtn = document.getElementById("next");
const passBtn = document.getElementById("pass");
const pauseBtn = document.getElementById("pause");
const quitBtn = document.getElementById("quit");
const statTotalQuestionsEl = document.getElementById("stat-total-questions");
const statTotalAnswersEl = document.getElementById("stat-total-answers");
const statCorrectEl = document.getElementById("stat-correct");
const statAccuracyEl = document.getElementById("stat-accuracy");
const statPassRateEl = document.getElementById("stat-passrate");
const statPassRatePasspoEl = document.getElementById("stat-passrate-passpo");
const statPassRateKihonEl = document.getElementById("stat-passrate-kihon");

const fastModeEl = document.getElementById("fast-mode");
const explainModeEl = document.getElementById("explain-mode");
const wrongOnlyEl = document.getElementById("wrong-only-mode");
const avoidCorrectEl = document.getElementById("avoid-correct-mode");
const randomModeEl = document.getElementById("random-mode");

fastModeEl.checked = true;
randomModeEl.checked = true;

const overlayEl = document.getElementById("overlay");
const overlayTextEl = document.getElementById("overlay-text");
const overlayCloseEl = document.getElementById("overlay-close");

let currentQuestion = null;
let selectedIndex = null;
let currentOrder = [];
let questionStartAt = null;

let totalQuestions = 0;
let totalAnswers = 0;
let correctCount = 0;

let sessionQuestions = [];
let sessionIndex = 0;
const pendingResults = [];

// LocalStorage key
const STORAGE_KEY = "quiz_user_state";

function getUserState() {
  const saved = localStorage.getItem(STORAGE_KEY);
  return saved ? JSON.parse(saved) : { questions: {}, totalAnswers: 0, correctCount: 0 };
}

function saveUserState(state) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function updateStatsDisplay() {
  const state = getUserState();
  // セッションの統計ではなく、累計の統計を表示するように変更（オプション）
  // ここでは表示用に現在のセッション変数を更新
  totalAnswers = state.totalAnswers;
  correctCount = state.correctCount;

  const accuracy = totalAnswers === 0 ? 0 : (correctCount / totalAnswers) * 100;
  const passRate =
    totalQuestions === 0 ? 0 : (correctCount / totalQuestions) * 100;

  // 試験区分別の統計
  let passpoTotal = 0;
  let passpoCorrect = 0;
  let kihonTotal = 0;
  let kihonCorrect = 0;

  // すべての読み込まれた問題に対してループ
  // sessionQuestions ではなく、読み込み時に保持している全データが必要だが、
  // 現状は sessionQuestions が全データ（またはフィルタ済みデータ）を保持している
  // 正確には全問題のカテゴリ情報が必要
  
  // 履歴データから試験区分別の正答数を集計
  // （全問題リスト sessionQuestions の各問題の id と category を参照）
  const categoryMap = {}; // id -> category
  sessionQuestions.forEach(q => {
    categoryMap[q.id] = q.category;
  });

  // 試験区分ごとの総問題数をカウント
  let passpoMax = 0;
  let kihonMax = 0;
  sessionQuestions.forEach(q => {
    if (q.category === "ITパスポート") passpoMax++;
    else kihonMax++;
  });

  Object.keys(state.questions).forEach(qid => {
    const s = state.questions[qid];
    const cat = categoryMap[qid];
    if (cat === "ITパスポート") {
      if (s.correct > 0) passpoCorrect++;
    } else if (cat === "基本情報") {
      if (s.correct > 0) kihonCorrect++;
    }
  });

  const passpoRate = passpoMax === 0 ? 0 : (passpoCorrect / passpoMax) * 100;
  const kihonRate = kihonMax === 0 ? 0 : (kihonCorrect / kihonMax) * 100;

  if (statTotalQuestionsEl) {
    statTotalQuestionsEl.textContent = String(totalQuestions);
  }
  if (statTotalAnswersEl) {
    statTotalAnswersEl.textContent = String(totalAnswers);
  }
  if (statCorrectEl) {
    statCorrectEl.textContent = String(correctCount);
  }
  if (statAccuracyEl) {
    statAccuracyEl.textContent = `${accuracy.toFixed(1)}%`;
  }
  if (statPassRateEl) {
    statPassRateEl.textContent = `${passRate.toFixed(1)}%`;
  }
  if (statPassRatePasspoEl) {
    statPassRatePasspoEl.textContent = `${passpoRate.toFixed(1)}%`;
  }
  if (statPassRateKihonEl) {
    statPassRateKihonEl.textContent = `${kihonRate.toFixed(1)}%`;
  }
}

async function startSession() {
  questionEl.textContent = "読み込み中...";
  optionsEl.innerHTML = "";
  feedbackEl.textContent = "";
  feedbackEl.className = "feedback";

  let useStaticFallback = false;

  try {
    const resMeta = await fetch(`${API_BASE}/api/v1/meta`);
    if (resMeta.ok) {
      const meta = await resMeta.json();
      totalQuestions = meta.totalQuestions || 0;
    } else {
      useStaticFallback = true;
    }
  } catch (_) {
    useStaticFallback = true;
  }

  if (useStaticFallback) {
    console.log("Using static fallback mode...");
    try {
      const [resKihon, resPasspo] = await Promise.all([
        fetch("./data/kihon.json"),
        fetch("./data/passpo.json")
      ]);
      
      const kihonData = resKihon.ok ? await resKihon.json() : [];
      const passpoData = resPasspo.ok ? await resPasspo.json() : [];
      
      const allQuestions = [];
      
      // 基本情報の正規化
      kihonData.forEach((item, i) => {
        const options = item.options || item.choices || [];
        const rawAnswer = item.answer;
        let ansIdx = 0;
        
        if (typeof rawAnswer === "string") {
          ansIdx = options.indexOf(rawAnswer);
          if (ansIdx === -1) ansIdx = 0;
        } else {
          ansIdx = (parseInt(rawAnswer) || 1) - 1;
        }

        allQuestions.push({
          id: item.id || `kihon_${i}`,
          category: item.category || "基本情報",
          question: item.question,
          options: options,
          answer: ansIdx,
          explanation: item.explanation
        });
      });
      
      // ITパスポートの正規化
      passpoData.forEach((item, i) => {
        const options = item.options || item.choices || [];
        const rawAnswer = item.answer;
        let ansIdx = 0;
        
        if (typeof rawAnswer === "string") {
          ansIdx = options.indexOf(rawAnswer);
          if (ansIdx === -1) ansIdx = 0;
        } else {
          ansIdx = (parseInt(rawAnswer) || 1) - 1;
        }
        
        allQuestions.push({
          id: item.id || `passpo_${i}`,
          category: item.category || "ITパスポート",
          question: item.question,
          options: options,
          answer: ansIdx,
          explanation: item.explanation
        });
      });
      
      if (useStaticFallback) {
        const state = getUserState();
        // 正解した問題をフィルタリング（一度も正解していない、または誤答がある問題を優先）
        sessionQuestions = allQuestions.filter(q => {
          const s = state.questions[q.id];
          return !s || s.correct === 0; // 正解数が0回のみ（一度でも正解したら出さない）
        });

        // 苦手度（誤答数）に基づいてソート
        sessionQuestions.sort((a, b) => {
          const sA = state.questions[a.id] || { wrong: 0, correct: 0 };
          const sB = state.questions[b.id] || { wrong: 0, correct: 0 };
          
          if (sA.wrong !== sB.wrong) return sB.wrong - sA.wrong;
          return Math.random() - 0.5;
        });
      } else {
        sessionQuestions = allQuestions;
        if (randomModeEl.checked) {
          shuffle(sessionQuestions);
        }
      }
      
      totalQuestions = sessionQuestions.length;
      sessionIndex = 0;
    } catch (e) {
      console.error("Static fallback failed:", e);
      questionEl.textContent = "データの読み込みに失敗しました";
      return;
    }
  } else {
    try {
      const params = new URLSearchParams({
        userId,
        limit: "100",
        wrongOnly: wrongOnlyEl.checked ? "1" : "0",
        avoidCorrect: avoidCorrectEl.checked ? "1" : "0",
        randomMode: randomModeEl.checked ? "1" : "0"
      });
      const resBatch = await fetch(
        `${API_BASE}/api/v1/questions/batch?${params.toString()}`
      );
      if (!resBatch.ok) {
        questionEl.textContent = "問題セットの取得に失敗しました";
        return;
      }
      const data = await resBatch.json();
      sessionQuestions = data.questions || [];
      sessionIndex = 0;
    } catch (_) {
      questionEl.textContent = "問題セットの取得に失敗しました";
      return;
    }
  }

  updateStatsDisplay();
  showNextQuestion();
}

function shuffle(array) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    const tmp = array[i];
    array[i] = array[j];
    array[j] = tmp;
  }
  return array;
}

function renderQuestion(q) {
  currentQuestion = q;
  selectedIndex = null;

  feedbackEl.textContent = "";
  feedbackEl.className = "feedback";
  optionsEl.innerHTML = "";

  if (!q) {
    questionEl.textContent = "問題がありません";
    return;
  }

  questionEl.textContent = q.question;
  questionStartAt = performance.now();
  
  const state = getUserState();
  const qState = state.questions[q.id];
  const prevWrongChoices = qState ? (qState.wrongChoices || []) : [];

  const indices = shuffle(q.options.map((_, i) => i));
  currentOrder = indices;
  indices.forEach((idx, displayIndex) => {
    const btn = document.createElement("button");
    btn.textContent = `${displayIndex + 1}. ${q.options[idx]}`;
    
    // 以前に間違えた選択肢であればクラスを追加
    if (prevWrongChoices.includes(idx)) {
      btn.classList.add("prev-wrong");
    }

    btn.addEventListener("click", () => selectOption(displayIndex, btn));
    optionsEl.appendChild(btn);
  });

  if (!fastModeEl.checked) {
    nextBtn.style.display = "block";
    nextBtn.disabled = true;
  } else {
    nextBtn.style.display = "none";
  }
}

function showNextQuestion() {
  if (!sessionQuestions.length) {
    questionEl.textContent = "セッションがありません。再読み込みしてください。";
    optionsEl.innerHTML = "";
    return;
  }
  if (sessionIndex >= sessionQuestions.length) {
    currentQuestion = null;
    optionsEl.innerHTML = "";
    feedbackEl.textContent = "セッションが完了しました";
    return;
  }
  const q = sessionQuestions[sessionIndex];
  sessionIndex += 1;
  renderQuestion(q);
}

function selectOption(i, btn) {
  if (!currentQuestion) return;
  selectedIndex = i;
  Array.from(optionsEl.children).forEach(b => b.classList.remove("selected"));
  btn.classList.add("selected");
  submitAnswer();
}

function showOverlay(text) {
  overlayTextEl.textContent = text || "解説ダミー（ここにMLの解説を表示）";
  overlayEl.classList.add("show");
}

function hideOverlay() {
  overlayEl.classList.remove("show");
}

async function submitAnswer() {
  if (selectedIndex == null || !currentQuestion) return;

  const now = performance.now();
  const elapsedMs =
    typeof questionStartAt === "number" ? Math.max(0, Math.round(now - questionStartAt)) : 0;

  pendingResults.push({
    questionId: currentQuestion.id,
    choice: currentOrder[selectedIndex],
    elapsedMs
  });

  const correctIndex = currentQuestion.answer;
  const chosenOriginalIndex = currentOrder[selectedIndex];
  const isCorrect = correctIndex === chosenOriginalIndex;

  // LocalStorage に結果を保存
  const state = getUserState();
  state.totalAnswers += 1;
  if (isCorrect) state.correctCount += 1;
  
  const qId = currentQuestion.id;
  if (!state.questions[qId]) {
    state.questions[qId] = { correct: 0, wrong: 0, lastAt: null, wrongChoices: [] };
  }
  if (isCorrect) {
    state.questions[qId].correct += 1;
    // 正解したらその問題の誤答履歴（ハイライト用）をリセットする場合
    // state.questions[qId].wrongChoices = []; 
  } else {
    state.questions[qId].wrong += 1;
    // どの選択肢を間違えたか記録（重複なし）
    if (!state.questions[qId].wrongChoices) state.questions[qId].wrongChoices = [];
    if (!state.questions[qId].wrongChoices.includes(chosenOriginalIndex)) {
      state.questions[qId].wrongChoices.push(chosenOriginalIndex);
    }
  }
  state.questions[qId].lastAt = new Date().toISOString();
  saveUserState(state);

  updateStatsDisplay();

  feedbackEl.classList.remove("correct", "wrong");
  if (!isCorrect) {
    feedbackEl.classList.add("wrong");
  }
  feedbackEl.textContent = isCorrect ? "正解" : "不正解";

  if (explainModeEl.checked) {
    showOverlay("解説ダミー（ここにMLの解説を表示）");
    if (!fastModeEl.checked) {
      nextBtn.disabled = false;
    }
  } else if (fastModeEl.checked) {
    setTimeout(showNextQuestion, 400);
  } else {
    nextBtn.disabled = false;
  }
}

nextBtn.addEventListener("click", () => {
  hideOverlay();
  showNextQuestion();
});

function passQuestion() {
  if (!currentQuestion) return;

  const now = performance.now();
  const elapsedMs =
    typeof questionStartAt === "number" ? Math.max(0, Math.round(now - questionStartAt)) : 0;

  pendingResults.push({
    questionId: currentQuestion.id,
    choice: -1,
    elapsedMs
  });

  totalAnswers += 1;
  updateStatsDisplay();

  feedbackEl.classList.remove("correct", "wrong");
  feedbackEl.textContent = "パス";

  setTimeout(showNextQuestion, fastModeEl.checked ? 200 : 400);
}

passBtn.addEventListener("click", passQuestion);

async function flushSessionResults() {
  if (!pendingResults.length) return;
  const payload = {
    userId,
    results: pendingResults.slice()
  };
  try {
    const res = await fetch(`${API_BASE}/api/v1/session/results`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      pendingResults.length = 0;
    }
  } catch (_) {}
}

pauseBtn.addEventListener("click", async () => {
  await flushSessionResults();
  feedbackEl.classList.remove("correct", "wrong");
  feedbackEl.textContent = "一時停止しました";
});

quitBtn.addEventListener("click", async () => {
  await flushSessionResults();
  sessionQuestions = [];
  sessionIndex = 0;
  currentQuestion = null;
  optionsEl.innerHTML = "";
  feedbackEl.classList.remove("correct", "wrong");
  feedbackEl.textContent = "セッションを終了しました";
  questionEl.textContent = "新しいセッションを開始するにはページを再読み込みしてください";
});

overlayCloseEl.addEventListener("click", () => {
  hideOverlay();
  if (fastModeEl.checked) {
    showNextQuestion();
  }
});

fastModeEl.addEventListener("change", () => {
  if (fastModeEl.checked) {
    nextBtn.style.display = "none";
  } else {
    nextBtn.style.display = "block";
  }
});

explainModeEl.addEventListener("change", () => {
  if (!fastModeEl.checked) {
    nextBtn.style.display = "block";
  }
});

startSession();
