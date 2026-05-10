"""
YouTube Analytics API から流入元（トラフィックソース）データを取得する。

取得項目（動画ごと・流入元タイプ別）:
    - YT_SEARCH:       YouTube内検索
    - RELATED_VIDEO:   関連動画
    - YT_CHANNEL:      チャンネルページ
    - SUBSCRIBER:      登録者の通知/フィード
    - PLAYLIST:        再生リスト
    - YT_OTHER_PAGE:   その他YouTube内
    - EXT_URL:         外部サイト
    - NO_LINK_OTHER:   ダイレクト
    - SHORTS:          ショート関連
    - HASHTAGS:        ハッシュタグ
    - NOTIFICATION:    通知
    - END_SCREEN:      終了画面
    その他多数
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
TRAFFIC_CSV = DATA_DIR / "traffic_sources.csv"

SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

CSV_FIELDS = [
    "snapshot_date",
    "period_start",
    "period_end",
    "video_id",
    "traffic_source_type",
    "views",
    "estimated_minutes_watched",
    "average_view_duration_sec",
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


def fetch_traffic_sources(analytics, video_id: str, start: str, end: str) -> list[dict]:
    """1動画の流入元別データを取得。"""
    response = (
        analytics.reports()
        .query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="views,estimatedMinutesWatched,averageViewDuration",
            dimensions="insightTrafficSourceType",
            filters=f"video=={video_id}",
            sort="-views",
            maxResults=25,
        )
        .execute()
    )

    rows = response.get("rows", [])
    column_headers = [h["name"] for h in response.get("columnHeaders", [])]
    key_map = {
        "insightTrafficSourceType": "traffic_source_type",
        "views": "views",
        "estimatedMinutesWatched": "estimated_minutes_watched",
        "averageViewDuration": "average_view_duration_sec",
    }
    results = []
    for row in rows:
        record = dict(zip(column_headers, row))
        results.append({key_map.get(k, k): v for k, v in record.items()})
    return results


def get_video_ids_from_recent_views(analytics, start: str, end: str) -> list[str]:
    """期間内に視聴があった動画IDのリストを取得（流入元クエリ対象を絞る）。"""
    response = (
        analytics.reports()
        .query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="views",
            dimensions="video",
            sort="-views",
            maxResults=200,
        )
        .execute()
    )
    return [row[0] for row in response.get("rows", [])]


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

    print(f"[traffic] {start_str} 〜 {end_str} の流入元データを取得")

    analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)

    # 期間内に視聴があった動画ID一覧を取得
    video_ids = get_video_ids_from_recent_views(analytics, start_str, end_str)
    print(f"[traffic] {len(video_ids)} 本の動画を対象に処理")

    all_rows: list[dict] = []
    for i, vid in enumerate(video_ids, 1):
        try:
            sources = fetch_traffic_sources(analytics, vid, start_str, end_str)
            for s in sources:
                all_rows.append(
                    {
                        "snapshot_date": snapshot_date,
                        "period_start": start_str,
                        "period_end": end_str,
                        "video_id": vid,
                        **s,
                    }
                )
        except Exception as e:
            print(f"[traffic] 動画 {vid} の取得に失敗: {e}", file=sys.stderr)
            continue

        if i % 10 == 0:
            print(f"[traffic] 進捗 {i}/{len(video_ids)}")

    append_csv(TRAFFIC_CSV, CSV_FIELDS, all_rows)
    print(f"[traffic] {len(all_rows)} 件を {TRAFFIC_CSV.name} に追記")
    return 0


if __name__ == "__main__":
    sys.exit(main())
