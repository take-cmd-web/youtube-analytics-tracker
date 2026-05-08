# YouTube Analytics Tracker

YouTubeチャンネルのパフォーマンス指標を毎日自動収集して、CSVに記録するシステムです。GitHub Actionsで定期実行されます。

## 取得する指標

### Data API v3（公開データ）
- チャンネル登録者数
- 各動画の再生回数、高評価数、コメント数
- 動画の長さ、投稿日時、タイトル、サムネイルURL

### Analytics API（自チャンネルのみ・OAuth認証必要）
- 平均視聴時間、平均視聴維持率
- 総再生時間
- インプレッション数、クリック率（CTR）
- トラフィックソース別の流入
- 新規視聴者 vs 再訪問視聴者
- 動画経由のチャンネル登録者増加数
- 共有数、再生リスト追加数

## ファイル構成

```
youtube-analytics-tracker/
├── README.md
├── requirements.txt
├── .gitignore
├── src/
│   ├── fetch_data_api.py       # 公開データ取得（Data API v3）
│   ├── fetch_analytics_api.py  # 詳細データ取得（Analytics API）
│   ├── manual_metadata.py      # 手動タグ付け用CSVテンプレ生成
│   └── auth_helper.py          # OAuth初回認証ヘルパー（ローカル実行用）
├── data/
│   ├── channel_daily.csv       # チャンネル単位の日次スナップショット
│   ├── videos_daily.csv        # 動画単位の日次スナップショット
│   ├── analytics_daily.csv     # Analytics APIからの詳細指標
│   └── manual_metadata.csv     # 手動入力するメタデータ（サムネ型など）
└── .github/workflows/
    └── daily_collect.yml       # 毎日定時実行するActions
```

## セットアップ手順

### 1. Google Cloud Console での準備

1. https://console.cloud.google.com/ で新規プロジェクト作成
2. 「APIとサービス」→「ライブラリ」で以下を有効化：
   - YouTube Data API v3
   - YouTube Analytics API
3. 「認証情報」で **APIキー** を発行（Data API用）
4. 「認証情報」で **OAuth 2.0 クライアントID** を発行（Analytics API用）
   - アプリケーションの種類：「デスクトップアプリ」
   - JSONをダウンロード

### 2. ローカルで初回OAuth認証

GitHub Actionsはブラウザを開けないため、初回だけローカルでトークンを取得します。

```bash
pip install -r requirements.txt
python src/auth_helper.py
```

ブラウザが開いてGoogleログイン → 許可 → `token.json` がローカルに生成されます。
このファイルの中身（refresh_token含む）をGitHub Secretsに登録します。

### 3. GitHub Secrets の登録

リポジトリの Settings → Secrets and variables → Actions → New repository secret

| Secret名 | 内容 |
|---|---|
| `YOUTUBE_API_KEY` | Data API用のAPIキー |
| `YT_CHANNEL_ID` | 自分のチャンネルID（UCで始まる文字列） |
| `OAUTH_CLIENT_JSON` | ダウンロードしたOAuthクライアントJSONの中身全体 |
| `OAUTH_TOKEN_JSON` | `token.json` の中身全体 |

### 4. 動作確認

GitHub上で Actions タブ → `Daily YouTube Metrics Collection` → `Run workflow` で手動実行できます。
成功すると `data/` 配下のCSVが更新され、自動コミットされます。

## 注意点

- **Analytics APIのデータは数日遅れて確定します。** 直近48時間は暫定値なので、固定タイミング（例：投稿後7日目）でスナップショットを取る分析と組み合わせると比較しやすくなります。
- **APIクォータ**：Data API v3は1日10,000ユニット。動画100本程度なら余裕です。
- **手動メタデータ**（サムネイル型・タイトル型・企画タグなど）は `data/manual_metadata.csv` に自分で追記してください。`manual_metadata.py` で雛形が生成できます。

## 分析の活用例

集まったCSVは、Pythonノートブックや Looker Studio、Google Sheets に読み込んで分析できます。
特に `videos_daily.csv` と `analytics_daily.csv` を `video_id` で結合し、`manual_metadata.csv` のタグを付与すると、「サムネイルに顔ありの動画は維持率が何%高いか」のようなパターン分析が可能になります。
