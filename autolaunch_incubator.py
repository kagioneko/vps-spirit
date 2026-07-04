#!/usr/bin/env python3
import os
import re
import sys
import json
import time
import requests
import subprocess
from datetime import datetime

# パス設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = "/home/mayutama/workspace/ai-microsaas"
HISTORY_FILE = os.path.join(ASSETS_DIR, "deploy_history.json")

# インポート用のディレクトリをパスに追加
sys.path.append(BASE_DIR)

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

def get_vault_secret(path, field):
    """Vaultから安全にシークレットを取得する"""
    env = os.environ.copy()
    env["VAULT_ADDR"] = "https://127.0.0.1:8200"
    env["VAULT_CACERT"] = "/etc/vault.d/tls/vault-cert.pem"
    try:
        proc = subprocess.run(
            ["vault", "kv", "get", f"-field={field}", path],
            capture_output=True, text=True, env=env, timeout=10
        )
        return proc.stdout.strip()
    except Exception:
        return None

def load_history():
    """過去のデプロイ履歴を読み込む"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(history):
    """デプロイ履歴を保存する"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def build_stripe_payment_link(app_name, idea):
    """Stripe APIを使用して、非インタラクティブに決済リンクを作成する"""
    api_key = get_vault_secret("secret/stripe", "api_key")
    if not api_key:
        print("[*] Stripe APIキーがVaultにありません。ダミー決済リンクを使用します。")
        return "https://checkout.stripe.com/pay/mock_paywall"
        
    try:
        import stripe
        stripe.api_key = api_key
        
        # 1. Product作成
        product = stripe.Product.create(
            name=f"{app_name} - Premium License",
            description=f"Lifetime Premium License for {app_name}. (Feature: {idea[:100]})"
        )
        # 2. Price作成 (500 JPY / $5 USD)
        price = stripe.Price.create(
            product=product.id,
            unit_amount=500,
            currency="usd",
        )
        # 3. 決済リンク作成
        payment_link = stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
        )
        return payment_link.url
    except Exception as e:
        print(f"[-] Stripeエラー: {e}。ダミーリンクを使用します。")
        return "https://checkout.stripe.com/pay/mock_paywall"

def build_cloudflare_pages(project_name, dist_dir):
    """Cloudflare Pagesへ非インタラクティブに自動デプロイする"""
    account_id = get_vault_secret("secret/cloudflare", "account_id")
    api_token = get_vault_secret("secret/cloudflare", "api_token")
    
    if not account_id or not api_token:
        print("[*] Cloudflare認証情報がVaultにありません。デプロイをスキップします（ローカル保存のみ）。")
        return None
        
    env = os.environ.copy()
    env["CLOUDFLARE_ACCOUNT_ID"] = account_id
    env["CLOUDFLARE_API_TOKEN"] = api_token
    
    cmd = [
        "npx", "-y", "wrangler", "pages", "deploy",
        dist_dir,
        "--project-name", project_name
    ]
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180)
        stdout_clean = re.sub(r'\x1b\[[0-9;]*m', '', proc.stdout)
        
        if proc.returncode == 0:
            url_match = re.search(r'https://[a-zA-Z0-9\-\.]+\.pages\.dev', stdout_clean)
            if url_match:
                return url_match.group(0)
    except Exception as e:
        print(f"[-] Wranglerデプロイ失敗: {e}")
    return None

def main():
    print("=" * 60)
    print("🤖 NekoGuard AI Autonomous SaaS Incubator Loop 🤖")
    print("=" * 60)
    
    # 1. 過去履歴の取得
    history = load_history()
    deployed_urls = {item["reddit_url"] for item in history if "reddit_url" in item}

    # 2. Reddit RSS からの需要データ収集
    print("[*] Reddit RSSから最新の需要データを取得中...")
    # demand_analyzerからRSS取得ロジックを借用
    from demand_analyzer import fetch_reddit_rss, analyze_rss_with_gemini
    
    xml_text = fetch_reddit_rss()
    if not xml_text:
        print("❌ 需要データ取得失敗。")
        return
        
    print("[*] Gemini による需要分析中...")
    ideas = analyze_rss_with_gemini(xml_text)
    if not ideas:
        print("❌ 分析失敗。")
        return

    # 未デプロイかつ最もスコアが高いものを1件選出
    target_idea = None
    for idea in sorted(ideas, key=lambda x: x.get("score", 0), reverse=True):
        url = idea.get("reddit_url")
        if url not in deployed_urls and idea.get("is_single_page_possible"):
            target_idea = idea
            break
            
    if not target_idea:
        print("💡 スキャンされた中に、新規で実装可能なアイデアはありませんでした。")
        return

    print(f"\n🏆 ローンチ候補選出:")
    print(f"   - タイトル: {target_idea['title_ja']}")
    print(f"   - 課題: {target_idea['pain_point_ja']}")
    print(f"   - スコア: {target_idea['score']}/10")
    print(f"   - 元スレッド: {target_idea['reddit_url']}")

    # 3. アプリ名とサニタイズ
    app_id = re.sub(r'[^a-zA-Z0-9]', '_', target_idea["title_en"])[:30].strip('_').lower()
    if not app_id:
        app_id = "auto_saas"
        
    project_name = re.sub(r'[^a-zA-Z0-9\-]', '-', app_id.replace('_', '-'))
    project_name = re.sub(r'\-+', '-', project_name).strip('-')
    readable_name = " ".join([w.capitalize() for w in app_id.split('_')])
    
    output_dir = os.path.join(ASSETS_DIR, app_id)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "index.html")

    # 4. Stripe決済リンクの発行
    checkout_url = build_stripe_payment_link(readable_name, target_idea["solution_ja"])

    # 5. アプリケーションコード（HTML）のビルド
    print(f"\n[*] アプリケーション生成中... 📍 出力先: {output_file}")
    
    system_instruction = (
        "You are an expert full-stack developer who creates stunning, single-file Micro-SaaS web applications. "
        "Your mission is to produce a single, self-contained index.html file that resolves the user's idea "
        "with rich aesthetics, high premium design (Tailwind CSS, DaisyUI, modern fonts, glassmorphism), "
        "and built-in Stripe paywall logic."
    )

    prompt = f"""
Create a highly professional and premium single-file HTML/JS Web Application based on this idea:
"{target_idea['title_en']}"

Requirements:
1. DESIGN & STYLE:
   - Use Tailwind CSS and DaisyUI via CDN.
   - Use Google Fonts (e.g. 'Outfit' or 'Inter') and custom color palettes (vibrant dark mode, premium glassmorphism gradients, elegant shadows).
   - It must look like a high-end SaaS homepage/tool, complete with a clean header, the core tool interface, and a pricing/licensing section.
   - Provide micro-animations or smooth transitions for active buttons and interactive states.

2. CORE FUNCTIONALITY:
   - Implement the actual working logic of the requested tool in pure client-side JavaScript.
   - The tool must be fully interactive.

3. STRIPE PAYWALL & MONETIZATION LOGIC:
   - Implement a premium licensing system in Javascript.
   - Set a usage limit for free users (e.g., maximum 3 operations, or a locked button for 'Export/Advanced' features).
   - Once the limit is hit, trigger a stunning Glassmorphism modal explaining that they have reached the limit.
   - In the modal, place a 'Buy Lifetime Access ($5)' button. You MUST set the href of this button to exactly: "{checkout_url}"
   - Provide an input field for a "License Key".
   - If the user enters the key 'SaaS-FREE-TEST-2026', unlock the full features immediately, show a success toast, and save the status as `isPremium = true` in `localStorage` so it persists between reloads.
   - The design must include a lock icon overlay or warning state for premium features.

4. MOBILE-FIRST RESPONSIVE MONETIZATION UI:
   - The entire application layout and paywall interface MUST be mobile-first responsive.
   - On small screens (smartphones), ensure all purchase call-to-actions (CTAs) are large and tap-friendly (minimum button height of 48px, plenty of touch padding).
   - Ensure the premium modal does not overflow and centers beautifully on mobile. Set input fields (like the License Key input) to a font size of at least 16px to prevent iOS devices from automatically zooming in when focusing the input field.

5. LEGAL & TRUST (DISCLAIMER / PRIVACY POLICY / ASCT):
   - At the bottom of the page (footer), implement clean, clickable links for "Privacy Policy", "Disclaimer", and "特定商取引法に基づく表記" (Act on Specified Commercial Transactions).
   - Clicking these links must trigger a small, elegant modal that clearly states:
     a) Privacy Policy: The app runs entirely in the client-side browser and utilizes `localStorage` for data persistence. No personal data or user inputs are collected or sent to external servers.
     b) Disclaimer: The tool is provided "as is" without any warranty of any kind. The developer is not liable for any data loss, damages, or issues arising from its usage.
     c) 特定商取引法に基づく表記: Display the following template in Japanese:
        - 販売業者/運営者: [運営者名 / 表示請求があった場合は遅滞なく開示します]
        - 連絡先メールアドレス: [サポート窓口メール / 表示請求があった場合は遅滞なく開示します。※プレースホルダー: support@example.com]
        - 住所・電話番号: 表示請求があった場合、遅滞なく電子メール等の書面にて提供いたします。
        - 販売価格: 各アプリ紹介・アップグレード画面に表示
        - 支払方法と時期: クレジットカード決済 (Stripe)。決済時に支払いが確定します。
        - 引渡時期: 決済完了後、即時（ライセンスキーの提供およびアクティベーション）。
        - 返品・キャンセル: デジタルコンテンツの性質上、購入後のキャンセルや返金はできません。

Return ONLY the raw HTML code inside a code block ```html ... ```. No additional conversational text.
"""
    
    response = run_gemini(prompt, system_instruction)
    if not response:
        print("❌ アプリケーションコードの生成失敗。")
        return
        
    html_code = ""
    match = re.search(r'```html(.*?)```', response, re.DOTALL)
    if match:
        html_code = match.group(1).strip()
    else:
        if "<html" in response:
            html_code = response.strip()
        else:
            print("❌ コード抽出失敗。")
            return
            
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_code)
    print("✅ アプリのソースコードをローカルに書き出しました。")

    # 6. Cloudflareへの自動デプロイ
    deployed_url = build_cloudflare_pages(project_name, output_dir)
    
    # 7. 履歴の保存
    new_launch = {
        "title_en": target_idea["title_en"],
        "title_ja": target_idea["title_ja"],
        "reddit_url": target_idea["reddit_url"],
        "stripe_url": checkout_url,
        "cloudflare_url": deployed_url if deployed_url else "Local Only",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    history.append(new_launch)
    save_history(history)

    print("\n" + "=" * 60)
    print("🚀 Auto-Launch Cycle Completed!")
    print("=" * 60)
    print(f"📍 アプリ名  : {readable_name}")
    print(f"📍 決済リンク: {checkout_url}")
    print(f"📍 公開URL   : {new_launch['cloudflare_url']}")
    print("=" * 60)

if __name__ == "__main__":
    main()
