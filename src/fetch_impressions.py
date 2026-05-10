"""
YouTube Analytics API からCTR・インプレッションデータを取得する。

チャンネルの規模・開設時期によって impressions / impressionsCtr が
利用できない場合があるため、まず impressions を試し、エラーなら
impressions なしで取得し直す。チャンネルが成長すれば自動的に
impressions データが解放される。
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

# impressions対応チャンネル用（フル指標）
METRICS_FULL = "views,estimatedMinutesWatched,impressions,impressionsCtr"

# impressions非対応チャンネル用（基本指標のみ）
METRICS_BASIC = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage"

CSV_FIELDS = [
    "snapshot_date",
    "period_start",
    "period_end",
    "video_id",
    "views",
    "estimated_minutes_watched",
    "average_view_duration_sec",
    "average_view_percentage",
    "impressions",        # 未対応チャンネルでは空欄
    "impressions_ctr",    # 未対応チャンネルでは空欄
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


def fetch_impressions(analytics, metrics: str, start: str, end: str) -> list[dict]:
    response = (
        analytics.reports()
        .query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics=metrics,
            dimensions="video",
            sort="-views",
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
        "averageViewDuration": "average_view_duration_sec",
        "averageViewPercentage": "average_view_percentage",
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

    # まずフル指標で試す
    try:
        rows = fetch_impressions(analytics, METRICS_FULL, start_str, end_str)
        print(f"[impressions] フル指標（impressions含む）で {len(rows)} 件取得")
    except Exception as e:
        # impressions非対応の場合は基本指標にフォールバック
        print(f"[impressions] impressions非対応のため基本指標で再取得: {e}", file=sys.stderr)
        try:
            rows = fetch_impressions(analytics, METRICS_BASIC, start_str, end_str)
            print(f"[impressions] 基本指標で {len(rows)} 件取得（impressions列は空欄）")
        except Exception as e2:
            print(f"[impressions] 基本指標でも失敗: {e2}", file=sys.stderr)
            return 1

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
