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

function updateStatsDisplay() {
  const accuracy = totalAnswers === 0 ? 0 : (correctCount / totalAnswers) * 100;
  const passRate =
    totalQuestions === 0 ? 0 : (correctCount / totalQuestions) * 100;

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
}

async function startSession() {
  questionEl.textContent = "読み込み中...";
  optionsEl.innerHTML = "";
  feedbackEl.textContent = "";
  feedbackEl.className = "feedback";

  try {
    const resMeta = await fetch(`${API_BASE}/api/v1/meta`);
    if (resMeta.ok) {
      const meta = await resMeta.json();
      totalQuestions = meta.totalQuestions || 0;
    }
  } catch (_) {}

  try {
    const params = new URLSearchParams({
      userId,
      limit: "30",
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
  const indices = shuffle(q.options.map((_, i) => i));
  currentOrder = indices;
  indices.forEach((idx, displayIndex) => {
    const btn = document.createElement("button");
    btn.textContent = `${displayIndex + 1}. ${q.options[idx]}`;
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

  totalAnswers += 1;
  if (isCorrect) correctCount += 1;
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
