"""
YouTube Analytics API からインプレッション・CTR データを取得する。

取得項目（動画ごと・期間集計）:
    - インプレッション数（サムネイルが表示された回数）
    - インプレッションCTR（クリック率%）
    - インプレッション経由の視聴時間（分）
    - インプレッション経由の平均視聴時間（秒）

注意:
    インプレッション系メトリクスは比較的新しく追加されたため、
    一部の古いチャンネルや特定の動画ではデータが取れない場合があります。
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
IMPRESSIONS_CSV = DATA_DIR / "impressions_ctr.csv"

SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

METRICS = ",".join(
    [
        "views",
        "estimatedMinutesWatched",
        "impressions",                # サムネ表示回数
        "impressionsCtr",              # CTR (%)
    ]
)

CSV_FIELDS = [
    "snapshot_date",
    "period_start",
    "period_end",
    "video_id",
    "views",
    "estimated_minutes_watched",
    "impressions",
    "impressions_ctr",
]


def load_credentials() -> Credentials:
    token_json = os.environ.get("OAUTH_TOKEN_JSON")
    client_json = os.environ.get("OAUTH_CLIENT_JSON")
    if not token_json or not client_json:
        raise RuntimeError("OAUTH_TOKEN_JSON / OAUTH_CLIENT_JSON が設定されていません")

    token_data = json.loads(token_json)
    client_data = json.loads(client_json)
    installed = client_data.get("installed") or client_data.get("web") or {}
    token_data.setdefault("client_id", installed.get("client_id"))
    token_data.setdefault("client_secret", installed.get("client_secret"))
    token_data.setdefault("token_uri", installed.get("token_uri", "https://oauth2.googleapis.com/token"))
    token_data.setdefault("scopes", SCOPES)
    return Credentials.from_authorized_user_info(token_data, scopes=SCOPES)


def fetch_impressions(analytics, start: str, end: str) -> list[dict]:
    response = (
        analytics.reports()
        .query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics=METRICS,
            dimensions="video",
            sort="-impressions",
            maxResults=200,
        )
        .execute()
    )

    column_headers = [h["name"] for h in response.get("columnHeaders", [])]
    rows = response.get("rows", [])

    key_map = {
        "video": "video_id",
        "views": "views",
        "estimatedMinutesWatched": "estimated_minutes_watched",
        "impressions": "impressions",
        "impressionsCtr": "impressions_ctr",
    }

    results: list[dict] = []
    for row in rows:
        record = dict(zip(column_headers, row))
        results.append({key_map.get(k, k): v for k, v in record.items()})
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

    today = datetime.now(timezone.utc).date()
    end_date = today - timedelta(days=4)
    start_date = end_date - timedelta(days=29)

    snapshot_date = today.strftime("%Y-%m-%d")
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    print(f"[impressions] {start_str} 〜 {end_str} のCTRデータを取得")

    analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    rows = fetch_impressions(analytics, start_str, end_str)
    print(f"[impressions] {len(rows)} 件のレコードを取得")

    enriched = [
        {
            "snapshot_date": snapshot_date,
            "period_start": start_str,
            "period_end": end_str,
            **r,
        }
        for r in rows
    ]
    append_csv(IMPRESSIONS_CSV, CSV_FIELDS, enriched)
    print(f"[impressions] {IMPRESSIONS_CSV.name} に追記完了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
