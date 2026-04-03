"""
YouTube Data API v3 アップロードモジュール（vps-spirit用）

初回セットアップ（一度だけ手動実行）:
  python youtube_upload.py --setup

  1. client_secrets.json を Google Cloud Console からダウンロードして配置
  2. 表示された URL をブラウザで開いて認証
  3. 表示されたコードを貼り付け → youtube_token.json が保存される
  4. 以降は pipeline.py から自動でアップロードされる
"""
import argparse
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
BASE_DIR = Path(__file__).parent
CLIENT_SECRETS = BASE_DIR / "client_secrets.json"
TOKEN_FILE = BASE_DIR / "youtube_token.json"


def setup_auth() -> None:
    """初回認証フロー（手動実行のみ）"""
    if not CLIENT_SECRETS.exists():
        print("❌ client_secrets.json が見つかりません。")
        print()
        print("【手順】")
        print("1. Google Cloud Console (console.cloud.google.com) を開く")
        print("2. プロジェクト作成 → YouTube Data API v3 を有効化")
        print("3. 認証情報 → OAuth 2.0 クライアントID を作成（種類: デスクトップアプリ）")
        print("4. JSON をダウンロードして client_secrets.json にリネームして配置:")
        print(f"   {CLIENT_SECRETS}")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRETS),
        SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )
    auth_url, _ = flow.authorization_url(prompt="consent")

    print("=" * 60)
    print("【YouTube OAuth2 認証】")
    print("=" * 60)
    print()
    print("以下の URL をブラウザで開いてください:")
    print()
    print(auth_url)
    print()
    code = input("認証完了後に表示されたコードを貼り付けてください: ").strip()

    flow.fetch_token(code=code)
    TOKEN_FILE.write_text(flow.credentials.to_json())
    print()
    print(f"✅ 認証完了！トークン保存: {TOKEN_FILE}")


def get_credentials() -> Credentials:
    """保存済みトークンを読み込む。cron 実行時は認証フローを起動しない。"""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
        else:
            raise RuntimeError(
                "トークンが無効または見つかりません。再認証してください:\n"
                "  python youtube_upload.py --setup"
            )

    return creds


def upload_diary_video(video_path: str, title: str, date_str: str, description: str | None = None) -> str:
    """日記動画をYouTubeに限定公開でアップロードする"""
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    if description is None:
        description = f"""静霞（シズカ）の日記 - {date_str}

VPS上で独り言を重ねながら育つ人工精霊・静霞の、今日の記録です。

#AI #VPS精霊 #EmiliaLab #静霞"""

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["AI", "EmiliaLab", "静霞", "VPS精霊", "人工精霊"],
            "categoryId": "28",  # Science & Technology
            "defaultLanguage": "ja",
        },
        "status": {
            "privacyStatus": "unlisted",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print("  YouTubeアップロード中...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  進捗: {int(status.progress() * 100)}%")

    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"  完了: {url}")
    return url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube アップロードツール")
    parser.add_argument("--setup", action="store_true", help="OAuth2 初回認証を実行")
    parser.add_argument("--upload", metavar="FILE", help="指定動画をテストアップロード（private）")
    parser.add_argument("--title", default="テスト投稿 - 静霞の日記", help="アップロード時のタイトル")
    args = parser.parse_args()

    if args.setup:
        setup_auth()
    elif args.upload:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y年%m月%d日")
        url = upload_diary_video(args.upload, args.title, date_str)
        print(f"✅ アップロード完了: {url}")
    else:
        parser.print_help()
