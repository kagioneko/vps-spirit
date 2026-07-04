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
        proc_id = subprocess.run(
            ["vault", "kv", "get", "-field=account_id", "secret/cloudflare"],
            capture_output=True, text=True, env=env, timeout=10
        )
        proc_token = subprocess.run(
            ["vault", "kv", "get", "-field=api_token", "secret/cloudflare"],
            capture_output=True, text=True, env=env, timeout=10
        )
        
        account_id = proc_id.stdout.strip()
        api_token = proc_token.stdout.strip()
        
        if account_id and api_token:
            return account_id, api_token
    except Exception as e:
        pass
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
    except Exception as e:
        print(f"❌ Vault書き込みエラー: {e}")
    return False

def get_stripe_key():
    """VaultからStripeのシークレットキーを取得する"""
    env = os.environ.copy()
    env["VAULT_ADDR"] = "https://127.0.0.1:8200"
    env["VAULT_CACERT"] = "/etc/vault.d/tls/vault-cert.pem"
    
    try:
        proc = subprocess.run(
            ["vault", "kv", "get", "-field=api_key", "secret/stripe"],
            capture_output=True, text=True, env=env, timeout=10
        )
        api_key = proc.stdout.strip()
        if api_key:
            return api_key
    except Exception as e:
        pass
    return None

def save_stripe_key(api_key):
    """StripeのAPIキーをVaultに保存する"""
    env = os.environ.copy()
    env["VAULT_ADDR"] = "https://127.0.0.1:8200"
    env["VAULT_CACERT"] = "/etc/vault.d/tls/vault-cert.pem"
    
    cmd = ["vault", "kv", "put", "secret/stripe", f"api_key={api_key}"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=10)
        if proc.returncode == 0:
            print("✅ StripeのAPIキーをVaultに安全に保存しました！")
            return True
    except Exception as e:
        print(f"❌ Vault書き込みエラー: {e}")
    return False

def generate_stripe_payment_link(app_name, idea):
    """Stripe APIを使用して自動で商品・価格・決済リンクを作成する"""
    print("\n" + "=" * 60)
    print("💳 Stripe 決済リンクを自動発行中...")
    print("=" * 60)
    
    api_key = get_stripe_key()
    
    if not api_key:
        print("💡 Stripe APIキーがVaultに見つかりません。")
        print("決済リンク自動生成のために、Stripeの『シークレットキー(sk_live_... / sk_test_...)』を入力してください。")
        print("(※何も入力せずにエンターを押すと、ダミーのテスト決済リンクを使用します)")
        api_key = input("🔑 Stripe Secret Key: ").strip()
        
        if not api_key:
            print("[*] キー入力をスキップしました。ダミーの決済リンクを使用します。")
            return "https://checkout.stripe.com/pay/mock_paywall"
        
        save_stripe_key(api_key)

    try:
        import stripe
        stripe.api_key = api_key
        
        # 1. Productの作成
        product = stripe.Product.create(
            name=f"{app_name} - Premium Access",
            description=f"Unlock lifetime unlimited access to {app_name}. (Feature: {idea[:100]})"
        )
        
        # 2. Priceの作成 (デフォルト: $5.00 USD)
        price = stripe.Price.create(
            product=product.id,
            unit_amount=500, # 500 = $5.00
            currency="usd",
        )
        
        # 3. Payment Linkの作成
        payment_link = stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
        )
        
        print(f"✅ Stripe決済リンクの発行に成功しました！")
        print(f"🔗 生成された決済リンク: {payment_link.url}")
        return payment_link.url
        
    except Exception as e:
        print(f"❌ Stripe接続/生成エラー: {e}")
        print("[*] フォールバックとして、ダミーのテスト決済リンクを使用します。")
        return "https://checkout.stripe.com/pay/mock_paywall"

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
        
        save_cloudflare_creds(account_id, api_token)

    print(f"[*] プロジェクト名: '{project_name}'")
    
    env = os.environ.copy()
    env["CLOUDFLARE_ACCOUNT_ID"] = account_id
    env["CLOUDFLARE_API_TOKEN"] = api_token
    env["CI"] = "true"
    
    # 存在しないプロジェクトを非インタラクティブで自動作成するために、事前に project create を走らせる
    print(f"[*] Cloudflare Pages プロジェクトを初期化中...")
    create_cmd = [
        "npx", "-y", "wrangler", "pages", "project", "create",
        project_name,
        "--production-branch", "main"
    ]
    # すでに存在する場合はエラーになるが、無視してデプロイに進む
    subprocess.run(create_cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("[*] Cloudflare Pages にデプロイを実行中...")
    cmd = [
        "npx", "-y", "wrangler", "pages", "deploy",
        dist_dir,
        "--project-name", project_name,
        "--branch", "main"
    ]
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180)
        stdout_clean = re.sub(r'\x1b\[[0-9;]*m', '', proc.stdout)
        stderr_clean = re.sub(r'\x1b\[[0-9;]*m', '', proc.stderr)
        
        if proc.returncode == 0:
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

def update_and_deploy_portal(new_app_info=None):
    """deploy_history.json を読み込み、ポータルサイトを再ビルドしてデプロイする"""
    import json
    from datetime import datetime
    print("\n" + "=" * 60)
    print("🌐 ポータルサイトの自動更新 & デプロイを実行中...")
    print("=" * 60)
    
    history_file = "/home/mayutama/workspace/ai-microsaas/deploy_history.json"
    history = []
    
    # 1. 履歴の読み込み
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass
            
    # 2. 新しいアプリ情報の追加 (重複チェック)
    if new_app_info:
        # 重複排除
        history = [item for item in history if item.get("cloudflare_url") != new_app_info.get("cloudflare_url")]
        history.append(new_app_info)
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            print("✅ デプロイ履歴ファイル (deploy_history.json) を更新しました。")
        except Exception as e:
            print(f"❌ 履歴ファイルの書き込みエラー: {e}")

    # 3. カードHTMLの生成
    card_templates = []
    for item in history:
        title = item.get("title_ja", item.get("title_en", "無題のアプリ"))
        desc = item.get("pain_point_ja", item.get("title_en", ""))
        url = item.get("cloudflare_url", "#")
        stripe_url = item.get("stripe_url", "")
        
        # 決済タイプ判別
        is_free = "mock_paywall" in stripe_url or not stripe_url
        price_badge = "Free" if is_free else "$5 Lifetime"
        if "journal" in url or "transl" in url or "completely-free" in url:
            price_badge = "Free (BYOK)"
        elif "crm" in url or "rewrit" in url:
            price_badge = "$9 Lifetime"
        
        # アイコンの動的決定
        icon = "sparkles"
        icon_color = "text-purple-400"
        bg_color = "bg-purple-500/10"
        border_color = "border-purple-500/20"
        
        if "bg-remover" in url or "one-click-bg" in url:
            icon, icon_color, bg_color, border_color = "scissors", "text-purple-400", "bg-purple-500/10", "border-purple-500/20"
        elif "jour" in url:
            icon, icon_color, bg_color, border_color = "book-open", "text-pink-400", "bg-pink-500/10", "border-pink-500/20"
        elif "transl" in url:
            icon, icon_color, bg_color, border_color = "languages", "text-blue-400", "bg-blue-500/10", "border-blue-500/20"
        elif "crm" in url:
            icon, icon_color, bg_color, border_color = "users", "text-indigo-400", "bg-indigo-500/10", "border-indigo-500/20"
        elif "health" in url or "wellness" in url:
            icon, icon_color, bg_color, border_color = "activity", "text-teal-400", "bg-teal-500/10", "border-teal-500/20"
        elif "converter" in url:
            icon, icon_color, bg_color, border_color = "image", "text-emerald-400", "bg-emerald-500/10", "border-emerald-500/20"
        elif "neko" in url or "mailbox" in url:
            icon, icon_color, bg_color, border_color = "mail animate-bounce", "text-orange-400", "bg-orange-500/10", "border-orange-500/20"
        elif "pitch" in url or "rewrit" in url:
            icon, icon_color, bg_color, border_color = "pen-tool", "text-rose-400", "bg-rose-500/10", "border-rose-500/20"

        badge_class = "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" if "Free" in price_badge else "bg-amber-500/10 text-amber-400 border border-amber-500/20"

        card_html = f"""
            <div class="app-card glass-panel premium-border p-6 rounded-2xl flex flex-col justify-between hover:scale-[1.02] transition-all duration-300" 
                 data-title="{title}" data-desc="{desc}" data-premium="{"false" if "Free" in price_badge else "true"}">
                <div>
                    <div class="flex justify-between items-start mb-4">
                        <div class="p-3 {bg_color} rounded-xl border {border_color} {icon_color}">
                            <i data-lucide="{icon.split(' ')[0]}" class="w-6 h-6 {"animate-bounce" if "bounce" in icon else ""}"></i>
                        </div>
                        <span class="badge {badge_class} font-bold">{price_badge}</span>
                    </div>
                    <h3 class="text-xl font-bold text-white mb-2">{title}</h3>
                    <p class="text-slate-300 text-sm leading-relaxed mb-6">
                        {desc}
                    </p>
                </div>
                <a href="{url}" target="_blank" class="btn btn-sm btn-outline border-white/10 hover:bg-purple-600 hover:border-purple-600 text-slate-200 w-full mt-auto flex items-center justify-center gap-1">
                    <span>アプリを開く</span>
                    <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
                </a>
            </div>"""
        card_templates.append(card_html)
        
    cards_combined = "\n".join(card_templates)

    # 4. テンプレートHTMLの準備
    portal_html = f"""<!DOCTYPE html>
<html lang="ja" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Micro-SaaS Factory | Showcase Portal</title>
    <link href="https://cdn.jsdelivr.net/npm/daisyui@4.12.10/dist/full.min.css" rel="stylesheet" type="text/css" />
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=Noto+Sans+JP:wght@300;400;500;700;900&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    fontFamily: {{
                        sans: ['Outfit', 'Noto Sans JP', 'sans-serif'],
                    }}
                }}
            }}
        }}
    </script>
    <style>
        .glass-panel {{
            background: rgba(15, 23, 42, 0.45);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }}
        .premium-border {{
            position: relative;
        }}
        .premium-border::after {{
            content: '';
            position: absolute;
            inset: 0;
            border-radius: inherit;
            padding: 1px;
            background: linear-gradient(135deg, rgba(139, 92, 246, 0.4) 0%, rgba(236, 72, 153, 0.4) 50%, rgba(245, 158, 11, 0.2) 100%);
            -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
            -webkit-mask-composite: xor;
            mask-composite: exclude;
            pointer-events: none;
        }}
        .filter-btn.active {{
            background: #8B5CF6;
            color: white;
            border-color: #8B5CF6;
        }}
    </style>
</head>
<body class="bg-slate-950 text-slate-100 font-sans min-h-screen relative overflow-x-hidden">
    <div class="absolute top-[-10%] left-[-10%] w-[600px] h-[600px] rounded-full bg-purple-900/10 blur-[130px] pointer-events-none"></div>
    <div class="absolute top-[40%] right-[-10%] w-[500px] h-[500px] rounded-full bg-pink-900/10 blur-[130px] pointer-events-none"></div>
    <div class="absolute bottom-[-10%] left-[20%] w-[700px] h-[700px] rounded-full bg-blue-900/10 blur-[150px] pointer-events-none"></div>

    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 md:py-20 relative z-10">
        <header class="text-center max-w-3xl mx-auto mb-12">
            <div class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-purple-500/10 border border-purple-500/30 text-purple-300 text-xs font-semibold mb-6">
                <i data-lucide="zap" class="w-3.5 h-3.5 text-purple-400 animate-pulse"></i>
                <span>完全自律型・インキュベーターAI</span>
            </div>
            <h1 class="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight leading-tight bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent mb-6">
                AI Micro-SaaS Factory
            </h1>
            <p class="text-slate-400 text-lg md:text-xl font-medium max-w-2xl mx-auto leading-relaxed">
                世の中の要望からAIが自動構築し、決済機能を備えた各種ミニWebアプリケーションのポートフォリオ。
            </p>
        </header>

        <!-- Stats Section -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-6 max-w-4xl mx-auto mb-12">
            <div class="glass-panel p-6 rounded-2xl text-center">
                <div class="text-slate-400 text-sm font-semibold mb-1">量産アプリ数</div>
                <div class="text-3xl md:text-4xl font-black bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">{len(history)}</div>
            </div>
            <div class="glass-panel p-6 rounded-2xl text-center">
                <div class="text-slate-400 text-sm font-semibold mb-1">デプロイ環境</div>
                <div class="text-xl md:text-2xl font-black text-slate-100 mt-2">Cloudflare</div>
            </div>
            <div class="glass-panel p-6 rounded-2xl text-center">
                <div class="text-slate-400 text-sm font-semibold mb-1">決済システム</div>
                <div class="text-xl md:text-2xl font-black text-slate-100 mt-2">Stripe</div>
            </div>
            <div class="glass-panel p-6 rounded-2xl text-center">
                <div class="text-slate-400 text-sm font-semibold mb-1">開発コスト / 個</div>
                <div class="text-3xl md:text-4xl font-black text-emerald-400">$0</div>
            </div>
        </div>

        <!-- 🔍 Search & Filter Bar -->
        <div class="max-w-4xl mx-auto mb-12 flex flex-col md:flex-row gap-4 items-center">
            <div class="relative w-full flex-1">
                <span class="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-slate-400">
                    <i data-lucide="search" class="w-5 h-5"></i>
                </span>
                <input id="searchInput" type="text" oninput="filterApps()" 
                       class="w-full pl-10 pr-4 py-3 bg-slate-900/60 border border-white/10 rounded-2xl text-slate-100 placeholder-slate-500 focus:outline-none focus:border-purple-500 text-base" 
                       placeholder="アプリ名やキーワードで検索...">
            </div>
            <div class="flex gap-2 w-full md:w-auto">
                <button onclick="setFilter('all', this)" class="filter-btn active btn btn-md border-white/10 bg-slate-900/60 text-slate-300 rounded-2xl flex-1 md:flex-initial">すべて</button>
                <button onclick="setFilter('paid', this)" class="filter-btn btn btn-md border-white/10 bg-slate-900/60 text-slate-300 rounded-2xl flex-1 md:flex-initial">有料 / プレミアム</button>
                <button onclick="setFilter('free', this)" class="filter-btn btn btn-md border-white/10 bg-slate-900/60 text-slate-300 rounded-2xl flex-1 md:flex-initial">無料 / BYOK</button>
            </div>
        </div>

        <!-- Grid Layout for SaaS Apps -->
        <div id="appsGrid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
{cards_combined}
        </div>

        <footer class="mt-28 border-t border-white/5 pt-8 text-center text-xs text-slate-500">
            <p>© {datetime.now().year} AI Micro-SaaS Factory. All rights reserved.</p>
        </footer>
    </div>

    <script>
        lucide.createIcons();
        let currentFilter = 'all';

        function setFilter(filterType, element) {{
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            element.classList.add('active');
            currentFilter = filterType;
            filterApps();
        }}

        function filterApps() {{
            const query = document.getElementById('searchInput').value.toLowerCase();
            const cards = document.querySelectorAll('.app-card');
            
            cards.forEach(card => {{
                const title = card.dataset.title.toLowerCase();
                const desc = card.dataset.desc.toLowerCase();
                const isPremium = card.dataset.premium === 'true';
                
                const matchesQuery = title.includes(query) || desc.includes(query);
                let matchesFilter = true;
                if (currentFilter === 'paid') matchesFilter = isPremium;
                if (currentFilter === 'free') matchesFilter = !isPremium;
                
                if (matchesQuery && matchesFilter) {{
                    card.style.display = 'flex';
                }} else {{
                    card.style.display = 'none';
                }}
            }});
        }}
    </script>
</body>
</html>"""
    
    # 5. 書き出し
    portal_dir = "/home/mayutama/workspace/ai-microsaas/portal"
    os.makedirs(portal_dir, exist_ok=True)
    output_file = os.path.join(portal_dir, "index.html")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(portal_html)
    print("✅ ポータルサイトのHTMLを再構築しました。")

    # 6. デプロイ
    account_id, api_token = get_cloudflare_creds()
    if not account_id or not api_token:
        print("❌ Cloudflare認証情報が見つかりません。ポータルのデプロイをスキップします。")
        return
        
    project_name = f"saas-factory-portal-{account_id[:6]}"
    print(f"[*] ポータルサイトをデプロイ中... ({project_name})")
    url = deploy_to_cloudflare(project_name, portal_dir)
    if url:
        print(f"\n🎉 ポータルShowcaseサイトが最新の状態に更新されました！")
        print(f"🌐 共有URL: {url}")

def main():
    print("=" * 60)
    print("🚀 AI Micro-SaaS Creator & Auto-Monetizer (Phase 1) 🚀")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        idea = " ".join(sys.argv[1:])
    else:
        idea = input("💡 作りたいアプリのアイデアを入力してください:\n> ")
        
    if not idea.strip():
        print("❌ アイデアが入力されていません。終了します。")
        return

    # 出力ファイル名用にディレクトリとアプリ名を定義
    # 日本語のアイデアからでも適切な英語のslugを生成するために、まずGeminiに適切な英語のプロジェクトID（英数字とハイフンのみ）を提案させる
    print("[*] アイデアに基づき、英語のプロジェクト名(Slug)を生成中...")
    slug_prompt = (
        f"Suggest a short, unique, lowercase English slug (using only a-z, 0-9, and hyphens, 8 to 20 characters) "
        f"that perfectly describes this app idea: '{idea}'. Output ONLY the slug, no other text."
    )
    suggested_slug = run_gemini(slug_prompt)
    if suggested_slug:
        # 余計なマークダウンや改行を除去
        suggested_slug = suggested_slug.strip().replace("`", "").split('\n')[0].strip()
        app_id = re.sub(r'[^a-z0-9\-]', '-', suggested_slug.lower())
        app_id = re.sub(r'\-+', '_', app_id).strip('_')
    else:
        app_id = re.sub(r'[^a-zA-Z0-9]', '_', idea)[:30].strip('_').lower()
        
    if not app_id or app_id == "1":
        app_id = "my_micro_saas"
        
    # Cloudflareプロジェクト名用にサニタイズ (英数字とハイフンのみ)し、競合を避けるために日付などのサフィックスを追加
    # 例: background-remover-260705
    from datetime import datetime
    suffix = datetime.now().strftime("%y%m%d")
    
    base_project_name = re.sub(r'[^a-zA-Z0-9\-]', '-', app_id.replace('_', '-'))
    base_project_name = re.sub(r'\-+', '-', base_project_name).strip('-')
    project_name = f"{base_project_name}-{suffix}"
    
    # 人間が読める形式のアプリ名に変換 (例: Image Converter)
    readable_name = " ".join([word.capitalize() for word in app_id.split('_')])

    # 1. 先にStripeの決済リンクを自動生成する
    checkout_url = generate_stripe_payment_link(readable_name, idea)

    output_dir = os.path.join("/home/mayutama/workspace/ai-microsaas", app_id)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "index.html")

    print(f"\n[*] アプリ名: '{readable_name}'")
    print(f"[*] アイデア: '{idea}'")
    print(f"[*] 決済用リンク: {checkout_url}")
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
            print("❌ レスンスからHTMLコードを抽出できませんでした。")
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
            
            # 履歴用のデータを作成し、ポータルを自動更新＆デプロイ
            from datetime import datetime
            new_app_info = {
                "title_en": readable_name,
                "title_ja": readable_name,
                "pain_point_ja": idea,
                "stripe_url": checkout_url,
                "cloudflare_url": deployed_url,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            update_and_deploy_portal(new_app_info)
    else:
        print("\n💡 ローカルでのテスト方法:")
        print("1. ブラウザで上記の HTML ファイルをダブルクリックして開きます。")
        print("2. 無料枠（制限回数）を使い切ると、ライセンスキー購入画面が開きます。")
        print("3. キーに「SaaS-FREE-TEST-2026」を入力してアンロックし、機能制限が解除されることを確認してください。")
        
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
