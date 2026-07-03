#!/usr/bin/env python3
import os
import re
import sys
import subprocess

def run_gemini(prompt, system_instruction=""):
    full_prompt = prompt
    if system_instruction:
        full_prompt = f"System: {system_instruction}\n\nUser: {prompt}"
    
    agy_path = os.path.expanduser("~/.local/bin/agy")
    if not os.path.exists(agy_path):
        agy_path = "agy"
        
    cmd = [agy_path, "-p", full_prompt]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        stdout_clean = re.sub(r'\x1b\[[0-9;]*m', '', proc.stdout)
        return stdout_clean.strip()
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return None

def get_cloudflare_creds():
    """VaultからCloudflareの認証情報を取得する"""
    env = os.environ.copy()
    env["VAULT_ADDR"] = "https://127.0.0.1:8200"
    env["VAULT_CACERT"] = "/etc/vault.d/tls/vault-cert.pem"
    
    try:
        # アカウントIDの取得
        proc_id = subprocess.run(
            ["vault", "kv", "get", "-field=account_id", "secret/cloudflare"],
            capture_output=True, text=True, env=env, timeout=10
        )
        # APIトークンの取得
        proc_token = subprocess.run(
            ["vault", "kv", "get", "-field=api_token", "secret/cloudflare"],
            capture_output=True, text=True, env=env, timeout=10
        )
        
        account_id = proc_id.stdout.strip()
        api_token = proc_token.stdout.strip()
        
        if account_id and api_token:
            return account_id, api_token
    except Exception as e:
        print(f"[*] Vaultアクセスエラー、またはキー未設定: {e}")
        
    return None, None

def save_cloudflare_creds(account_id, api_token):
    """入力されたCloudflare認証情報をVaultに保存する"""
    env = os.environ.copy()
    env["VAULT_ADDR"] = "https://127.0.0.1:8200"
    env["VAULT_CACERT"] = "/etc/vault.d/tls/vault-cert.pem"
    
    cmd = [
        "vault", "kv", "put", "secret/cloudflare",
        f"account_id={account_id}",
        f"api_token={api_token}"
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=10)
        if proc.returncode == 0:
            print("✅ Cloudflareの認証情報をVaultに安全に保存しました！")
            return True
        else:
            print(f"❌ Vaultへの保存に失敗しました: {proc.stderr}")
    except Exception as e:
        print(f"❌ Vault書き込みエラー: {e}")
    return False

def deploy_to_cloudflare(project_name, dist_dir):
    """Cloudflare Pagesへプロジェクトをデプロイする"""
    print("\n" + "=" * 60)
    print("🌐 Cloudflare Pages へのデプロイを準備中...")
    print("=" * 60)
    
    account_id, api_token = get_cloudflare_creds()
    
    if not account_id or not api_token:
        print("💡 Cloudflareの認証情報がVaultに見つかりません。")
        print("自動デプロイのために情報を入力してください (入力値はVaultに自動で永続保存されます)。")
        account_id = input("🔑 Cloudflare Account ID: ").strip()
        api_token = input("🔑 Cloudflare API Token (Pages edit permission): ").strip()
        
        if not account_id or not api_token:
            print("❌ 入力がキャンセルされました。デプロイをスキップします。")
            return False
        
        # Vaultに保存
        save_cloudflare_creds(account_id, api_token)

    print(f"[*] プロジェクト名: '{project_name}'")
    print("[*] Cloudflare Pages にデプロイを実行中...")
    
    # Wrangler用の環境変数を設定して実行
    env = os.environ.copy()
    env["CLOUDFLARE_ACCOUNT_ID"] = account_id
    env["CLOUDFLARE_API_TOKEN"] = api_token
    
    # wrangler pages deploy <directory> --project-name <name>
    cmd = [
        "npx", "-y", "wrangler", "pages", "deploy",
        dist_dir,
        "--project-name", project_name
    ]
    
    try:
        # 非インタラクティブで実行してログを取得
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180)
        
        # 出力をクリーンアップ
        stdout_clean = re.sub(r'\x1b\[[0-9;]*m', '', proc.stdout)
        stderr_clean = re.sub(r'\x1b\[[0-9;]*m', '', proc.stderr)
        
        if proc.returncode == 0:
            # ログから公開用URLを抽出 (例: https://xxx.pages.dev)
            url_match = re.search(r'https://[a-zA-Z0-9\-\.]+\.pages\.dev', stdout_clean)
            deployed_url = url_match.group(0) if url_match else "不明 (ダッシュボードを確認してください)"
            
            print("\n🎉 Cloudflare Pages へのデプロイが成功しました！")
            print(f"🌐 公開URL: {deployed_url}")
            return deployed_url
        else:
            print(f"\n❌ デプロイが失敗しました (Exit Code: {proc.returncode})")
            print("--- Wrangler Error Logs ---")
            print(stderr_clean)
            print(stdout_clean)
    except Exception as e:
        print(f"❌ Wrangler実行エラー: {e}")
        
    return False

def main():
    print("=" * 60)
    print("🚀 AI Micro-SaaS Creator & Deployer (Phase 1) 🚀")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        idea = " ".join(sys.argv[1:])
    else:
        idea = input("💡 作りたいアプリのアイデアを入力してください:\n> ")
        
    if not idea.strip():
        print("❌ アイデアが入力されていません。終了します。")
        return

    # 出力ファイル名用にディレクトリとアプリ名を定義
    app_id = re.sub(r'[^a-zA-Z0-9]', '_', idea)[:30].strip('_').lower()
    if not app_id:
        app_id = "my_micro_saas"
        
    # Cloudflareプロジェクト名用にサニタイズ (英数字とハイフンのみ)
    project_name = re.sub(r'[^a-zA-Z0-9\-]', '-', app_id.replace('_', '-'))
    project_name = re.sub(r'\-+', '-', project_name).strip('-')

    output_dir = os.path.join("/home/mayutama/workspace/ai-microsaas", app_id)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "index.html")

    print(f"\n[*] アイデア: '{idea}'")
    print(f"[*] ターゲット出力先: {output_file}")
    print("[*] Geminiにアプリの設計と実装を指示中... (これには1〜2分程度かかる場合があります)")

    system_instruction = (
        "You are an expert full-stack developer who creates stunning, single-file Micro-SaaS web applications. "
        "Your mission is to produce a single, self-contained index.html file that resolves the user's idea "
        "with rich aesthetics, high premium design (Tailwind CSS, DaisyUI, modern fonts, glassmorphism), "
        "and built-in Stripe paywall logic."
    )

    prompt = f"""
Create a highly professional and premium single-file HTML/JS Web Application based on this idea:
"{idea}"

Requirements:
1. DESIGN & STYLE:
   - Use Tailwind CSS and DaisyUI via CDN.
   - Use Google Fonts (e.g. 'Outfit' or 'Inter') and custom color palettes (vibrant dark mode, premium glassmorphism gradients, elegant shadows). Avoid browser default fonts and generic plain colors.
   - It must look like a high-end SaaS homepage/tool, complete with a clean header, the core tool interface, and a pricing/licensing section.
   - Provide micro-animations or smooth transitions for active buttons and interactive states.

2. CORE FUNCTIONALITY:
   - Implement the actual working logic of the requested tool in pure client-side JavaScript.
   - If the tool requires heavy APIs, mock them beautifully or use free public APIs. The tool must be fully interactive.

3. STRIPE PAYWALL & MONETIZATION LOGIC:
   - Implement a premium licensing system in Javascript.
   - Set a usage limit for free users (e.g., maximum 3 operations, or a locked button for 'Export/Advanced' features).
   - Once the limit is hit, trigger a stunning Glassmorphism modal explaining that they have reached the limit.
   - In the modal, place a 'Buy Lifetime Access ($5)' button pointing to a mockup checkout URL (e.g., 'https://checkout.stripe.com/pay/mock_paywall').
   - Provide an input field for a "License Key".
   - If the user enters the key 'SaaS-FREE-TEST-2026', unlock the full features immediately, show a success toast, and save the status as `isPremium = true` in `localStorage` so it persists between reloads.
   - The design must include a lock icon overlay or warning state for premium features.

Return ONLY the raw HTML code inside a code block ```html ... ```. No additional conversational text.
"""

    response = run_gemini(prompt, system_instruction)
    
    if not response:
        print("❌ アプリケーションの作成に失敗しました。")
        return

    # ```html ``` ブロックからコードを抽出
    html_code = ""
    match = re.search(r'```html(.*?)```', response, re.DOTALL)
    if match:
        html_code = match.group(1).strip()
    else:
        if "<html" in response:
            html_code = response.strip()
        else:
            print("❌ レスポンスからHTMLコードを抽出できませんでした。")
            return

    # ファイルに保存
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_code)

    print("\n" + "=" * 60)
    print("🎉 アプリケーションの自動生成が完了しました！")
    print("=" * 60)
    print(f"📍 ローカル保存場所: [index.html](file://{output_file})")
    
    # デプロイ確認
    deploy_choice = input("\n🌐 Cloudflare Pages に自動デプロイしますか？ (y/n): ").strip().lower()
    if deploy_choice == 'y':
        deployed_url = deploy_to_cloudflare(project_name, output_dir)
        if deployed_url:
            print("\n🚀 デプロイ完了しました！")
            print(f"   本番公開URL: {deployed_url}")
            print(f"   (Stripeのダミーキー「SaaS-FREE-TEST-2026」で制限解除して動作テストを行ってください)")
    else:
        print("\n💡 ローカルでのテスト方法:")
        print("1. ブラウザで上記の HTML ファイルをダブルクリックして開きます。")
        print("2. 無料枠（制限回数）を使い切ると、ライセンスキー購入画面が開きます。")
        print("3. キーに「SaaS-FREE-TEST-2026」を入力してアンロックし、機能制限が解除されることを確認してください。")
        
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
