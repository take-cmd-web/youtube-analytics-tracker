"""
初回OAuth認証ヘルパー（ローカル実行用）

GitHub Actionsはブラウザを開けないため、初回認証はローカルで行います。
このスクリプトを実行するとブラウザが開き、Google認証後に
token.json が生成されます。その中身をGitHub Secretsに登録してください。

使い方:
    1. Google Cloud ConsoleでダウンロードしたOAuthクライアントJSONを
       このディレクトリに client_secret.json として保存
    2. python src/auth_helper.py を実行
    3. ブラウザでGoogleログイン → 許可
    4. 生成された token.json の中身全体を、
       GitHub Secrets の OAUTH_TOKEN_JSON に登録
"""

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

# YouTube Analytics APIの読み取り権限
SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.json"


def main() -> None:
    if not Path(CLIENT_SECRET_FILE).exists():
        raise SystemExit(
            f"{CLIENT_SECRET_FILE} が見つかりません。\n"
            "Google Cloud Consoleで作成したOAuthクライアントJSONを"
            f"このディレクトリに {CLIENT_SECRET_FILE} という名前で保存してください。"
        )

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    # access_type=offline + prompt=consent で確実にrefresh_tokenを取得
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )

    Path(TOKEN_FILE).write_text(creds.to_json(), encoding="utf-8")

    print(f"\n✅ {TOKEN_FILE} を生成しました。")
    print("\n次の手順:")
    print(f"  1. {TOKEN_FILE} の中身全体をコピー")
    print("  2. GitHubリポジトリの Settings → Secrets and variables → Actions")
    print("  3. New repository secret で OAUTH_TOKEN_JSON という名前で貼り付け")
    print(f"  4. client_secret.json の中身も OAUTH_CLIENT_JSON として登録")
    print(f"\n⚠️  {TOKEN_FILE} と {CLIENT_SECRET_FILE} は絶対にコミットしないでください")
    print("    （.gitignoreに登録済みです）")


if __name__ == "__main__":
    main()
