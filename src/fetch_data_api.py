"""
YouTube Data API v3 から公開データを取得し、CSVに追記する。

取得項目:
    チャンネル: 登録者数、総再生回数、動画本数
    動画ごと: 再生回数、高評価数、コメント数、タイトル、公開日、動画長

使い方:
    環境変数:
        YOUTUBE_API_KEY: Data API用のAPIキー
        YT_CHANNEL_ID:   自分のチャンネルID（UCで始まる）
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.discovery import build

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CHANNEL_CSV = DATA_DIR / "channel_daily.csv"
VIDEOS_CSV = DATA_DIR / "videos_daily.csv"

CHANNEL_FIELDS = [
    "snapshot_date",
    "channel_id",
    "subscriber_count",
    "view_count",
    "video_count",
]

VIDEO_FIELDS = [
    "snapshot_date",
    "video_id",
    "title",
    "published_at",
    "duration",
    "view_count",
    "like_count",
    "comment_count",
    "thumbnail_url",
]


def get_youtube_client(api_key: str):
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def fetch_channel_stats(youtube, channel_id: str) -> dict:
    """チャンネル統計とアップロード再生リストIDを取得。"""
    response = (
        youtube.channels()
        .list(part="statistics,contentDetails", id=channel_id)
        .execute()
    )
    items = response.get("items", [])
    if not items:
        raise RuntimeError(f"チャンネルID {channel_id} が見つかりませんでした")

    item = items[0]
    stats = item["statistics"]
    uploads_playlist_id = item["contentDetails"]["relatedPlaylists"]["uploads"]

    return {
        "subscriber_count": int(stats.get("subscriberCount", 0)),
        "view_count": int(stats.get("viewCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "uploads_playlist_id": uploads_playlist_id,
    }


def fetch_all_video_ids(youtube, uploads_playlist_id: str) -> list[str]:
    """アップロード再生リストから全動画IDを取得（ページング対応）。"""
    video_ids: list[str] = []
    page_token: str | None = None

    while True:
        response = (
            youtube.playlistItems()
            .list(
                part="contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=page_token,
            )
            .execute()
        )
        for item in response.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return video_ids


def fetch_video_details(youtube, video_ids: list[str]) -> list[dict]:
    """動画詳細を50件ずつバッチで取得。"""
    results: list[dict] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        response = (
            youtube.videos()
            .list(part="snippet,statistics,contentDetails", id=",".join(batch))
            .execute()
        )
        for item in response.get("items", []):
            snippet = item["snippet"]
            stats = item.get("statistics", {})
            content = item["contentDetails"]
            thumbnails = snippet.get("thumbnails", {})
            # 高画質サムネのURLを優先取得
            thumbnail_url = (
                thumbnails.get("maxres", {}).get("url")
                or thumbnails.get("high", {}).get("url")
                or thumbnails.get("default", {}).get("url", "")
            )
            results.append(
                {
                    "video_id": item["id"],
                    "title": snippet["title"],
                    "published_at": snippet["publishedAt"],
                    "duration": content["duration"],  # ISO 8601 (例: PT5M30S)
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "thumbnail_url": thumbnail_url,
                }
            )
    return results


def append_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    """CSVに追記。ファイルがなければヘッダー付きで新規作成。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def main() -> int:
    api_key = os.environ.get("YOUTUBE_API_KEY")
    channel_id = os.environ.get("YT_CHANNEL_ID")

    if not api_key or not channel_id:
        print("ERROR: YOUTUBE_API_KEY と YT_CHANNEL_ID を環境変数で設定してください", file=sys.stderr)
        return 1

    snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    youtube = get_youtube_client(api_key)

    # チャンネル統計
    channel_stats = fetch_channel_stats(youtube, channel_id)
    append_csv(
        CHANNEL_CSV,
        CHANNEL_FIELDS,
        [
            {
                "snapshot_date": snapshot_date,
                "channel_id": channel_id,
                "subscriber_count": channel_stats["subscriber_count"],
                "view_count": channel_stats["view_count"],
                "video_count": channel_stats["video_count"],
            }
        ],
    )
    print(
        f"[channel] subscribers={channel_stats['subscriber_count']} "
        f"views={channel_stats['view_count']} videos={channel_stats['video_count']}"
    )

    # 動画詳細
    video_ids = fetch_all_video_ids(youtube, channel_stats["uploads_playlist_id"])
    print(f"[videos] {len(video_ids)} 本の動画を発見")

    video_details = fetch_video_details(youtube, video_ids)
    rows = [{"snapshot_date": snapshot_date, **v} for v in video_details]
    append_csv(VIDEOS_CSV, VIDEO_FIELDS, rows)
    print(f"[videos] {len(rows)} 件を {VIDEOS_CSV.name} に追記")

    return 0


if __name__ == "__main__":
    sys.exit(main())
