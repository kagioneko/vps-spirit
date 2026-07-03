#!/usr/bin/env python3
import os
import re
import sys
import json
import requests
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
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        stdout_clean = re.sub(r'\x1b\[[0-9;]*m', '', proc.stdout)
        return stdout_clean.strip()
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return None

def fetch_reddit_rss(subreddit="somebodymakethis"):
    """RedditからRSSフィードをテキストとして取得する"""
    url = f"https://www.reddit.com/r/{subreddit}/new.rss"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.text
        else:
            print(f"❌ Reddit RSS エラー (Status Code: {response.status_code})")
    except Exception as e:
        print(f"❌ Reddit RSS 取得失敗: {e}")
    return None

def analyze_rss_with_gemini(xml_text):
    """取得したRSS XML全体をGeminiに流し込んで一括分析・スコアリングする"""
    system_instruction = (
        "You are an expert market analyst and SaaS product manager. "
        "Your task is to parse the raw Reddit RSS XML feed, extract software ideas, "
        "translate them to Japanese, summarize problem/solution, "
        "and output them in a structured JSON format sorted by monetization potential and ease of implementation."
    )
    
    prompt = f"""
Below is the raw RSS XML data from /r/somebodymakethis (Reddit).
Please:
1. Parse the <entry> items and extract the software development requests/ideas.
2. Filter out non-software requests or spam.
3. For each valid idea, evaluate if it is feasible to build as a client-side Single-Page Web App (pure HTML/CSS/JS with localStorage, no database, no backend).
4. Translate and summarize the Problem (Pain Point) and Solution (App Feature) in Japanese.
5. Score the feasibility/monetization potential from 1 to 10 (10 being highly demanding, very easy to implement as single-page, and highly monetizable).
6. Return the top 5 candidates as a JSON array of objects.

Input XML Feed:
{xml_text[:50000]}  # トークン制限に配慮して念のためスライス

Required Output JSON Format:
[
  {{
    "title_en": "Original English Title or Short Summary of the idea",
    "is_single_page_possible": true/false,
    "title_ja": "日本語のアプリ名称/アイデアのタイトル",
    "pain_point_ja": "ユーザーの抱える不満や課題の日本語要約",
    "solution_ja": "求められるアプリのコア機能の日本語要約",
    "score": 1-10,
    "reasoning_ja": "スコアをつけた理由の日本語説明",
    "reddit_url": "The link of the post (extract from <link href=...>)"
  }}
]

Return ONLY the raw JSON array. Do not include markdown code fence wrappers (like ```json).
"""
    response = run_gemini(prompt, system_instruction)
    if not response:
        return None
        
    try:
        json_clean = response.strip()
        if json_clean.startswith("```"):
            json_clean = re.sub(r'^```[a-z]*\n|```$', '', json_clean, flags=re.MULTILINE).strip()
            
        result = json.loads(json_clean)
        return result
    except Exception as e:
        # デバッグ用に出力を少し出す
        # print(f"DEBUG: Parse fail. Raw output start: {response[:300]}")
        return None

def main():
    print("=" * 60)
    print("🔍 AI Demand Analyzer (Reddit RSS Micro-SaaS Finder) 🔍")
    print("=" * 60)
    
    subreddit = "somebodymakethis"
    
    print(f"[*] Reddit (r/{subreddit}) からRSSフィードを取得中...")
    xml_text = fetch_reddit_rss(subreddit)
    
    if not xml_text:
        print("❌ XMLデータを取得できませんでした。終了します。")
        return
        
    print("✅ RSSフィードの取得に成功しました。")
    print("[*] Gemini による一括需要分析とスコアリングを開始します...")
    
    analyzed_ideas = analyze_rss_with_gemini(xml_text)
    
    if not analyzed_ideas:
        print("❌ Geminiによる需要分析結果のパースに失敗しました。")
        return
        
    # スコアの降順でソート
    analyzed_ideas.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    # ファイル保存
    output_dir = "/home/mayutama/workspace/ai-microsaas"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "demand_list.json")
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(analyzed_ideas, f, indent=2, ensure_ascii=False)
        
    print("\n" + "=" * 60)
    print("🎉 需要リサーチ＆スコアリングが完了しました！")
    print("=" * 60)
    print(f"📍 結果ファイル: [demand_list.json](file://{output_file})")
    print(f"📍 有効なシングルページ開発候補案: {len(analyzed_ideas)} 件")
    print("=" * 60)
    
    # 結果の上位を表示
    for idx, idea in enumerate(analyzed_ideas[:3], 1):
        print(f"\n🏆 候補案 #{idx} (SaaS適合スコア: {idea['score']}/10)")
        print(f"   🔹 アプリ案: {idea['title_ja']}")
        print(f"   🔹 ユーザーの課題: {idea['pain_point_ja']}")
        print(f"   🔹 解決策(機能): {idea['solution_ja']}")
        print(f"   🔹 スコア理由: {idea['reasoning_ja']}")
        if 'reddit_url' in idea:
            print(f"   🔗 Redditスレッド: {idea['reddit_url']}")
        print("   " + "-" * 50)
        
    if analyzed_ideas:
        print("\n💡 開発のヒント:")
        print("  - 上記の候補案のタイトルをそのまま `microsaas_creator.py` に引数として渡すだけで、")
        print("    即座にStripe決済付きのプロダクトが自動生成されます！")
        print(f"  - コマンド例:\n    python3 /home/mayutama/workspace/vps-spirit/microsaas_creator.py \"{analyzed_ideas[0]['title_en']}\"")
    print("=" * 60)

if __name__ == "__main__":
    main()
