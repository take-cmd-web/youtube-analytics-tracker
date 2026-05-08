"""
手動メタデータCSVの雛形を生成する。

videos_daily.csv に存在するが manual_metadata.csv に未登録の
video_id について、空の行を追加する。あとは表計算ソフト等で
サムネイルパターンやタイトル型を手動入力していく想定。

使い方:
    python src/manual_metadata.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VIDEOS_CSV = DATA_DIR / "videos_daily.csv"
MANUAL_CSV = DATA_DIR / "manual_metadata.csv"

FIELDS = [
    "video_id",
    "title",                   # 参照用（自動コピー）
    "thumbnail_pattern",       # 例: face_yes, face_no, text_heavy, minimal
    "title_pattern",           # 例: list, question, hook, plain
    "genre_tag",               # 例: tutorial, vlog, review
    "hook_type",               # 例: question, surprise, problem, demo
    "notes",
]


def load_existing_video_ids() -> set[str]:
    if not MANUAL_CSV.exists():
        return set()
    with MANUAL_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["video_id"] for row in reader if row.get("video_id")}


def load_videos_with_titles() -> dict[str, str]:
    """videos_daily.csvから最新のタイトル一覧をvideo_id→titleで取得。"""
    if not VIDEOS_CSV.exists():
        print(f"ERROR: {VIDEOS_CSV} が見つかりません。先に fetch_data_api.py を実行してください")
        sys.exit(1)

    latest: dict[str, str] = {}
    with VIDEOS_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 後勝ちなので最終的に最新のスナップショットのタイトルが残る
            latest[row["video_id"]] = row.get("title", "")
    return latest


def main() -> int:
    existing = load_existing_video_ids()
    videos = load_videos_with_titles()

    new_ids = [vid for vid in videos if vid not in existing]
    if not new_ids:
        print("新しい動画はありません。manual_metadata.csv は最新です。")
        return 0

    file_exists = MANUAL_CSV.exists()
    with MANUAL_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not file_exists:
            writer.writeheader()
        for vid in new_ids:
            writer.writerow(
                {
                    "video_id": vid,
                    "title": videos[vid],
                    "thumbnail_pattern": "",
                    "title_pattern": "",
                    "genre_tag": "",
                    "hook_type": "",
                    "notes": "",
                }
            )

    print(f"{len(new_ids)} 件の動画行を {MANUAL_CSV.name} に追加しました。")
    print("表計算ソフトで開いて、各列を手動入力してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
