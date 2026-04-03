import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path
from urllib.parse import urlparse, parse_qs

flow = InstalledAppFlow.from_client_secrets_file(
    'client_secrets.json',
    ['https://www.googleapis.com/auth/youtube.upload'],
    redirect_uri='http://localhost'
)
url, _ = flow.authorization_url(prompt='consent')

print("以下のURLをブラウザで開いてください:\n")
print(url)
print()

redirect = input('リダイレクト後のURLを丸ごと貼り付け: ').strip()
code = parse_qs(urlparse(redirect).query)['code'][0]
flow.fetch_token(code=code)
Path('youtube_token.json').write_text(flow.credentials.to_json())
print('認証完了！youtube_token.json を保存しました')
