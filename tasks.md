# TASKS.API 連携用タスク一覧

## Backend

- **api_questions_next**
  - `GET /api/v1/questions/next` を実装する
  - 引数: `userId`, `wrongOnly`, `avoidCorrect`, `random` など
  - Python 側で FSRS＋正誤履歴にもとづき「次の1問」を決定して返す

- **api_meta**
  - `GET /api/v1/meta` を実装する
  - 全問題数 `totalQuestions` とジャンル一覧 `categories[{ name, count }]` を返す

- **api_plan**
  - `GET /api/v1/plan` を実装する
  - 引数: `userId`, `examDate`, `targetRounds`
  - Firestore の `answers.elapsedMs` と `meta.totalQuestions` から残り日数と 1 日あたり必要学習時間を計算して返す

- **api_category_stats**
  - `GET /api/v1/stats/categories` を実装する
  - 引数: `userId`
  - ジャンルごとの `total / answered / correct` を返し、グラフ描画の元データにする

- **api_questions_batch_5**
  - `GET /api/v1/questions/batch` を実装する
  - 引数: `userId`, `limit`（デフォルト 5）
  - FSRS＋正誤履歴にもとづき「今やるべき問題」を最大 5 問返す

## Frontend

- **fe_use_questions_next**
  - `main.js` を修正し `/api/v1/questions` を直接読むのを廃止する
  - 毎回 `GET /api/v1/questions/next` を叩いて出題するクライアントにリファクタする

- **fe_plan_stats_integration**
  - STATS デッキに試験日と周回目標の入力 UI を追加する
  - `GET /api/v1/plan` の結果（残り日数・ 1 日あたり必要学習時間）を STATS 内に表示する

- **fe_category_charts**
  - `stats/categories` の結果を用いてジャンル別正誤率の円グラフとスター型ダイアグラムを描画する
  - 表示 ON/OFF のトグルを STATS デッキに追加する

- **fe_quick5_mode**
  - MODE もしくは STATS デッキに「隙間時間で 5 問やる」ボタンを追加する
  - 押下で `/api/v1/questions/batch?limit=5` を呼び出し、5 問分だけ最速モードで流す
