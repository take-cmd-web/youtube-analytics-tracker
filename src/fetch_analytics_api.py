"""
YouTube Analytics API から自チャンネルの詳細指標を取得し、CSVに追記する。

取得項目（動画ごと・日別）:
    - 視聴回数、推定視聴時間（分）、平均視聴時間（秒）
    - 平均視聴維持率（%）
    - インプレッション数、CTR
    - 高評価/低評価/コメント/共有/再生リスト追加
    - チャンネル登録獲得数/解除数

使い方:
    環境変数:
        OAUTH_CLIENT_JSON: OAuthクライアントJSONの中身（文字列）
        OAUTH_TOKEN_JSON:  認証済みtoken.jsonの中身（文字列）
                           ※ refresh_token を含むこと
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ANALYTICS_CSV = DATA_DIR / "analytics_daily.csv"

SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

# Analytics APIで一度に取得する指標
METRICS = ",".join(
    [
        "views",
        "estimatedMinutesWatched",
        "averageViewDuration",       # 秒
        "averageViewPercentage",     # %
        "likes",
        "dislikes",                  # APIでは取得可能（公開はされない）
        "comments",
        "shares",
        "subscribersGained",
        "subscribersLost",
        "videosAddedToPlaylists",
    ]
)

# CTR/インプレッションは別エンドポイント（traffic source等と同じくfilters組み合わせが必要）
IMPRESSION_METRICS = "cardImpressions,cardClickRate"  # 参考。実用は下のCTR用クエリ

CSV_FIELDS = [
    "snapshot_date",
    "report_date",        # 集計対象日
    "video_id",
    "views",
    "estimated_minutes_watched",
    "average_view_duration_sec",
    "average_view_percentage",
    "likes",
    "dislikes",
    "comments",
    "shares",
    "subscribers_gained",
    "subscribers_lost",
    "videos_added_to_playlists",
]


def load_credentials() -> Credentials:
    """環境変数から認証情報を読み込む。GitHub Actions実行用。"""
    token_json = os.environ.get("OAUTH_TOKEN_JSON")
    client_json = os.environ.get("OAUTH_CLIENT_JSON")

    if not token_json:
        raise RuntimeError("環境変数 OAUTH_TOKEN_JSON が設定されていません")
    if not client_json:
        raise RuntimeError("環境変数 OAUTH_CLIENT_JSON が設定されていません")

    token_data = json.loads(token_json)
    client_data = json.loads(client_json)

    # OAuthクライアント情報を補完（refresh時に必要）
    installed = client_data.get("installed") or client_data.get("web") or {}
    token_data.setdefault("client_id", installed.get("client_id"))
    token_data.setdefault("client_secret", installed.get("client_secret"))
    token_data.setdefault("token_uri", installed.get("token_uri", "https://oauth2.googleapis.com/token"))
    token_data.setdefault("scopes", SCOPES)

    return Credentials.from_authorized_user_info(token_data, scopes=SCOPES)


def fetch_video_analytics(
    analytics,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """指定期間の動画別Analytics指標を取得。"""
    response = (
        analytics.reports()
        .query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics=METRICS,
            dimensions="day,video",
            sort="day",
            maxResults=200,
        )
        .execute()
    )

    column_headers = [h["name"] for h in response.get("columnHeaders", [])]
    rows = response.get("rows", [])

    # APIのキャメルケースをCSVのスネークケースに変換するマッピング
    key_map = {
        "day": "report_date",
        "video": "video_id",
        "views": "views",
        "estimatedMinutesWatched": "estimated_minutes_watched",
        "averageViewDuration": "average_view_duration_sec",
        "averageViewPercentage": "average_view_percentage",
        "likes": "likes",
        "dislikes": "dislikes",
        "comments": "comments",
        "shares": "shares",
        "subscribersGained": "subscribers_gained",
        "subscribersLost": "subscribers_lost",
        "videosAddedToPlaylists": "videos_added_to_playlists",
    }

    results: list[dict] = []
    for row in rows:
        record = dict(zip(column_headers, row))
        normalized = {key_map.get(k, k): v for k, v in record.items()}
        results.append(normalized)
    return results


def append_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def main() -> int:
    try:
        creds = load_credentials()
    except Exception as e:
        print(f"ERROR: 認証情報の読み込みに失敗: {e}", file=sys.stderr)
        return 1

    # Analytics APIは数日遅れて確定するため、4日前〜2日前を対象にする
    today = datetime.now(timezone.utc).date()
    end_date = today - timedelta(days=2)
    start_date = today - timedelta(days=4)

    snapshot_date = today.strftime("%Y-%m-%d")
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    print(f"[analytics] {start_str} 〜 {end_str} のデータを取得")

    analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    rows = fetch_video_analytics(analytics, start_str, end_str)
    print(f"[analytics] {len(rows)} 件のレコードを取得")

    enriched = [{"snapshot_date": snapshot_date, **r} for r in rows]
    append_csv(ANALYTICS_CSV, CSV_FIELDS, enriched)
    print(f"[analytics] {ANALYTICS_CSV.name} に追記完了")

    return 0


if __name__ == "__main__":
    sys.exit(main())
