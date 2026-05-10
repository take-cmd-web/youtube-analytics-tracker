"""
YouTube Analytics API から視聴維持率カーブ（リテンションカーブ）を取得する。

取得項目（動画ごと・時間軸 0.0-1.0 の各点）:
    - audienceWatchRatio:   絶対視聴維持率（その時点で見ている視聴者の割合）
    - relativeRetentionPerformance: 相対視聴維持率（YouTube平均と比較した値）

elapsedVideoTimeRatioは0.0〜1.0の相対時間で100ポイント刻みで返ります。
動画長が分かれば「動画開始から○秒時点での維持率」に変換できます。

注意:
    1動画ごとに1リクエスト必要なので、動画数が多いとAPIコール数が増えます。
    対象期間は過去30日（4日前まで）の視聴があった動画に絞っています。
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
RETENTION_CSV = DATA_DIR / "retention_curves.csv"

SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

CSV_FIELDS = [
    "snapshot_date",
    "period_start",
    "period_end",
    "video_id",
    "elapsed_video_time_ratio",       # 0.0〜1.0
    "audience_watch_ratio",            # 絶対維持率
    "relative_retention_performance",  # 相対維持率
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


def get_video_ids_from_recent_views(analytics, start: str, end: str) -> list[str]:
    response = (
        analytics.reports()
        .query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="views",
            dimensions="video",
            sort="-views",
            maxResults=50,  # 上位50動画のみ（API消費を抑える）
        )
        .execute()
    )
    return [row[0] for row in response.get("rows", [])]


def fetch_retention(analytics, video_id: str, start: str, end: str) -> list[dict]:
    """1動画の視聴維持率カーブを取得（101ポイント程度）。"""
    response = (
        analytics.reports()
        .query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="audienceWatchRatio,relativeRetentionPerformance",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}",
        )
        .execute()
    )

    rows = response.get("rows", [])
    column_headers = [h["name"] for h in response.get("columnHeaders", [])]
    key_map = {
        "elapsedVideoTimeRatio": "elapsed_video_time_ratio",
        "audienceWatchRatio": "audience_watch_ratio",
        "relativeRetentionPerformance": "relative_retention_performance",
    }
    results = []
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

    print(f"[retention] {start_str} 〜 {end_str} の視聴維持率カーブを取得")

    analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)

    video_ids = get_video_ids_from_recent_views(analytics, start_str, end_str)
    print(f"[retention] {len(video_ids)} 本の動画を対象に処理")

    all_rows: list[dict] = []
    for i, vid in enumerate(video_ids, 1):
        try:
            curve = fetch_retention(analytics, vid, start_str, end_str)
            for point in curve:
                all_rows.append(
                    {
                        "snapshot_date": snapshot_date,
                        "period_start": start_str,
                        "period_end": end_str,
                        "video_id": vid,
                        **point,
                    }
                )
        except Exception as e:
            print(f"[retention] 動画 {vid} の取得に失敗: {e}", file=sys.stderr)
            continue

        if i % 10 == 0:
            print(f"[retention] 進捗 {i}/{len(video_ids)}")

    append_csv(RETENTION_CSV, CSV_FIELDS, all_rows)
    print(f"[retention] {len(all_rows)} 件を {RETENTION_CSV.name} に追記")
    return 0


if __name__ == "__main__":
    sys.exit(main())
