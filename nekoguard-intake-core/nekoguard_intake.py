#!/usr/bin/env python3
import os
import sys
import json
import hashlib
import time
import subprocess
from datetime import datetime

# 危険とみなす拡張子のリスト (Review判定用)
SUSPICIOUS_EXTENSIONS = {
    '.exe', '.scr', '.vbs', '.bat', '.cmd', '.lnk', '.sh', '.bin', 
    '.msi', '.ps1', '.sys', '.dll', '.cpl', '.hta', '.jar'
}

def get_sha256(filepath):
    """ファイルのSHA256ハッシュを計算する"""
    sha256 = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        return f"ERROR: {str(e)}"

def run_clamscan(filepath):
    """ClamAVによるスキャンを実行する (インストールされていない場合はモック動作)"""
    # 簡易的にEICARテストファイル（ウイルス検知テスト用ダミー）を模倣
    try:
        with open(filepath, 'r', errors='ignore') as f:
            content = f.read(100)
            if "X5O!P%@AP[4\\PZX54(P^)7CC7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*" in content:
                return "Danger: Eicar-Test-Signature Detected"
    except Exception:
        pass

    # 本番の Clamscan 実行を試みる
    if os.system("which clamscan > /dev/null 2>&1") == 0:
        try:
            proc = subprocess.run(["clamscan", "--no-summary", filepath], capture_output=True, text=True, timeout=30)
            if proc.returncode == 1: # ウイルス検知
                match = re.search(r':\s+(.*?)\s+FOUND', proc.stdout)
                virus_name = match.group(1) if match else "Malware"
                return f"Danger: {virus_name} Detected"
            elif proc.returncode == 0:
                return "Clean"
        except Exception as e:
            return f"Scan Error: {str(e)}"
    
    return "Clean (Mock)"

def run_yarascan(filepath, rules_path=None):
    """YARAによるスキャンを実行する (インストールされていない場合はモック動作)"""
    # EICARテストの模擬検知
    try:
        with open(filepath, 'r', errors='ignore') as f:
            content = f.read(100)
            if "X5O!P%@AP[4\\PZX54(P^)7CC7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*" in content:
                return ["EICAR_Test_Rule"]
    except Exception:
        pass

    # 本番の YARA 実行を試みる
    if rules_path and os.path.exists(rules_path) and os.system("which yara > /dev/null 2>&1") == 0:
        try:
            proc = subprocess.run(["yara", rules_path, filepath], capture_output=True, text=True, timeout=10)
            if proc.returncode == 0 and proc.stdout.strip():
                matches = []
                for line in proc.stdout.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 1:
                        matches.append(parts[0])
                return matches
        except Exception:
            pass
            
    return [] # 検知なし

def scan_directory(target_path, rules_path=None):
    """ディレクトリ全体をスキャンし、各ファイルの状態とリスク判定を行う"""
    start_time = time.time()
    results = []
    
    print(f"[*] スキャンを開始します: {target_path}")
    
    # 対象が単一ファイルの場合とディレクトリの場合に対応
    files_to_scan = []
    if os.path.isfile(target_path):
        files_to_scan.append(target_path)
    elif os.path.isdir(target_path):
        for root, _, filenames in os.walk(target_path):
            for filename in filenames:
                files_to_scan.append(os.path.join(root, filename))
    else:
        print(f"❌ 対象が見つかりません: {target_path}")
        sys.exit(1)

    danger_count = 0
    review_count = 0
    safe_count = 0

    for filepath in files_to_scan:
        rel_path = os.path.relpath(filepath, target_path)
        filename = os.path.basename(filepath)
        size = os.path.getsize(filepath)
        
        # 1. ハッシュ計算
        sha256 = get_sha256(filepath)
        
        # 2. ClamAV
        clam_res = run_clamscan(filepath)
        
        # 3. YARA
        yara_res = run_yarascan(filepath, rules_path)
        
        # 4. 拡張子と隠しファイルのチェック
        ext = os.path.splitext(filename)[1].lower()
        is_suspicious_ext = ext in SUSPICIOUS_EXTENSIONS
        is_hidden = filename.startswith('.')
        
        # 5. リスク判定 (Verdict)
        verdict = "Safe"
        reasons = []
        
        if "Danger" in clam_res:
            verdict = "Danger"
            reasons.append(clam_res)
        if yara_res:
            verdict = "Danger"
            reasons.append(f"YARA Match: {', '.join(yara_res)}")
            
        if verdict != "Danger":
            if is_suspicious_ext:
                verdict = "Review"
                reasons.append(f"Suspicious extension ({ext})")
            if is_hidden:
                verdict = "Review"
                reasons.append("Hidden file")
            if size > 100 * 1024 * 1024: # 100MB超え
                verdict = "Review"
                reasons.append("Unusually large file (>100MB)")

        # カウント更新
        if verdict == "Danger":
            danger_count += 1
        elif verdict == "Review":
            review_count += 1
        else:
            safe_count += 1

        results.append({
            "filename": filename,
            "path": rel_path,
            "size_bytes": size,
            "sha256": sha256,
            "clamav": clam_res,
            "yara": yara_res,
            "verdict": verdict,
            "reasons": reasons
        })
        
    duration = time.time() - start_time
    
    # 最終的な判定
    final_verdict = "Safe"
    if danger_count > 0:
        final_verdict = "Danger"
    elif review_count > 0:
        final_verdict = "Review"

    summary = {
        "target_path": target_path,
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "final_verdict": final_verdict,
        "total_files": len(files_to_scan),
        "danger_files": danger_count,
        "review_files": review_count,
        "safe_files": safe_count,
        "scan_duration_sec": round(duration, 3),
        "files": results
    }
    
    return summary

def generate_reports(summary, output_dir):
    """JSONおよび美しいHTMLレポートを生成する"""
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. JSON レポートの書き出し
    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"✅ JSONレポートを保存しました: {json_path}")
    
    # 2. HTML レポートの生成
    html_path = os.path.join(output_dir, "report.html")
    
    # 最終判定に応じたカラーテーマ定義
    verdict_colors = {
        "Safe": {
            "bg": "bg-emerald-950/40",
            "border": "border-emerald-500/30",
            "text": "text-emerald-400",
            "badge": "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
            "icon": "shield-check"
        },
        "Review": {
            "bg": "bg-amber-950/40",
            "border": "border-amber-500/30",
            "text": "text-amber-400",
            "badge": "bg-amber-500/10 text-amber-400 border-amber-500/20",
            "icon": "alert-triangle"
        },
        "Danger": {
            "bg": "bg-rose-950/40",
            "border": "border-rose-500/30",
            "text": "text-rose-400",
            "badge": "bg-rose-500/10 text-rose-400 border-rose-500/20",
            "icon": "shield-alert"
        }
    }
    
    color = verdict_colors[summary["final_verdict"]]
    
    # ファイルリストを行に変換
    file_rows = []
    for f in summary["files"]:
        row_color = verdict_colors[f["verdict"]]["text"]
        badge_class = verdict_colors[f["verdict"]]["badge"]
        reasons_text = ", ".join(f["reasons"]) if f["reasons"] else "-"
        
        row_html = f"""
        <tr class="hover:bg-slate-900/60 border-b border-slate-800 transition-colors duration-200">
          <td class="px-6 py-4 font-semibold text-white truncate max-w-xs" title="{f['filename']}">{f['filename']}</td>
          <td class="px-6 py-4 text-slate-400 text-sm truncate max-w-md" title="{f['path']}">{f['path']}</td>
          <td class="px-6 py-4 text-slate-400 text-sm">{f['size_bytes']:,} B</td>
          <td class="px-6 py-4"><span class="px-2.5 py-1 rounded-full text-xs font-semibold border {badge_class}">{f['verdict']}</span></td>
          <td class="px-6 py-4 text-xs font-mono text-slate-500 truncate max-w-[120px]" title="{f['sha256']}">{f['sha256'][:16]}...</td>
          <td class="px-6 py-4 text-sm {row_color} font-medium">{reasons_text}</td>
        </tr>
        """
        file_rows.append(row_html)
        
    html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NekoGuard Intake - 検査レポート</title>
  
  <!-- Google Fonts - Outfit -->
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
  
  <!-- Tailwind CSS & DaisyUI -->
  <link href="https://cdn.jsdelivr.net/npm/daisyui@4.12.10/dist/full.min.css" rel="stylesheet" type="text/css" />
  <script src="https://cdn.tailwindcss.com"></script>
  
  <!-- Lucide Icons -->
  <script src="https://cdn.jsdelivr.net/npm/lucide@0.399.0/dist/umd/lucide.min.js"></script>

  <style>
    body {{
      font-family: 'Outfit', sans-serif;
      background: radial-gradient(circle at 50% 0%, rgba(99, 102, 241, 0.08) 0%, rgba(15, 23, 42, 0) 50%), #0b0f19;
    }}
    .glass-card {{
      background: rgba(15, 23, 42, 0.6);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
    }}
  </style>
</head>
<body class="text-slate-200 min-h-screen flex flex-col antialiased">

  <!-- Header -->
  <header class="w-full bg-slate-950/60 border-b border-slate-900 py-6 px-8">
    <div class="max-w-7xl mx-auto flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="bg-indigo-600/20 p-2.5 rounded-xl border border-indigo-500/30">
          <i data-lucide="shield" class="w-6 h-6 text-indigo-400"></i>
        </div>
        <div>
          <span class="text-xl font-extrabold tracking-tight text-white">NekoGuard Intake</span>
          <span class="block text-[10px] text-indigo-400 font-bold tracking-widest uppercase">Quarantine Report</span>
        </div>
      </div>
      <div class="text-slate-500 text-xs font-semibold">v0.1 Core Scanner</div>
    </div>
  </header>

  <!-- Main Content -->
  <main class="flex-grow max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-10">
    
    <!-- Hero Verdict Banner -->
    <div class="rounded-3xl border p-8 mb-10 glass-card flex flex-col md:flex-row items-center gap-8 {color['bg']} {color['border']}">
      <div class="p-5 rounded-2xl bg-slate-950/60 border {color['border']} flex items-center justify-center">
        <i data-lucide="{color['icon']}" class="w-16 h-16 {color['text']}"></i>
      </div>
      <div class="text-center md:text-left flex-grow">
        <span class="text-sm font-semibold tracking-widest uppercase opacity-70">Inspection Result</span>
        <h1 class="text-4xl md:text-5xl font-extrabold tracking-tight text-white mt-1 mb-2">
          Verdict: <span class="{color['text']}">{summary['final_verdict']}</span>
        </h1>
        <p class="text-slate-400">
          Target Path: <code class="bg-slate-950/80 px-2.5 py-1 rounded-md text-slate-300 font-mono text-sm">{summary['target_path']}</code>
        </p>
      </div>
      <div class="flex md:flex-col gap-4 text-center md:text-right border-t md:border-t-0 md:border-l border-slate-800 pt-6 md:pt-0 md:pl-8">
        <div>
          <span class="block text-slate-500 text-[10px] uppercase font-bold tracking-widest">Scanned At</span>
          <span class="text-sm font-semibold text-slate-300">{summary['scanned_at']}</span>
        </div>
        <div>
          <span class="block text-slate-500 text-[10px] uppercase font-bold tracking-widest">Duration</span>
          <span class="text-sm font-semibold text-slate-300">{summary['scan_duration_sec']}s</span>
        </div>
      </div>
    </div>

    <!-- Statistics Grid -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-6 mb-10">
      <div class="glass-card border border-slate-800 rounded-2xl p-6">
        <span class="block text-slate-500 text-xs uppercase font-bold tracking-widest mb-1">Total Files</span>
        <span class="text-3xl font-extrabold text-white">{summary['total_files']}</span>
      </div>
      <div class="glass-card border border-slate-800 rounded-2xl p-6 border-l-4 border-l-rose-500">
        <span class="block text-slate-500 text-xs uppercase font-bold tracking-widest mb-1">Danger Files</span>
        <span class="text-3xl font-extrabold text-rose-400">{summary['danger_files']}</span>
      </div>
      <div class="glass-card border border-slate-800 rounded-2xl p-6 border-l-4 border-l-amber-500">
        <span class="block text-slate-500 text-xs uppercase font-bold tracking-widest mb-1">Review Files</span>
        <span class="text-3xl font-extrabold text-amber-400">{summary['review_files']}</span>
      </div>
      <div class="glass-card border border-slate-800 rounded-2xl p-6 border-l-4 border-l-emerald-500">
        <span class="block text-slate-500 text-xs uppercase font-bold tracking-widest mb-1">Safe Files</span>
        <span class="text-3xl font-extrabold text-emerald-400">{summary['safe_files']}</span>
      </div>
    </div>

    <!-- File List Table -->
    <div class="glass-card border border-slate-800 rounded-3xl overflow-hidden shadow-2xl">
      <div class="px-8 py-6 bg-slate-900/40 border-b border-slate-800 flex items-center justify-between">
        <h2 class="text-lg font-bold text-white">Scanned Files Detail</h2>
        <span class="text-xs text-slate-500 font-mono">List sorted by scanning order</span>
      </div>
      <div class="overflow-x-auto">
        <table class="table w-full border-collapse">
          <thead>
            <tr class="bg-slate-950/40 border-b border-slate-800 text-slate-400 text-xs font-bold uppercase tracking-wider">
              <th class="px-6 py-4">File Name</th>
              <th class="px-6 py-4">Relative Path</th>
              <th class="px-6 py-4">File Size</th>
              <th class="px-6 py-4">Verdict</th>
              <th class="px-6 py-4">SHA256</th>
              <th class="px-6 py-4">Scan Details</th>
            </tr>
          </thead>
          <tbody>
            {"".join(file_rows)}
          </tbody>
        </table>
      </div>
    </div>

  </main>

  <!-- Footer -->
  <footer class="w-full bg-slate-950/60 border-t border-slate-900 py-6 text-center text-slate-500 text-xs">
    <div class="max-w-7xl mx-auto">
      NekoGuard Intake Core - Inspect First, Connect Later.
    </div>
  </footer>

  <script>
    lucide.createIcons();
  </script>
</body>
</html>
"""
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"✅ HTMLレポートを保存しました: {html_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 nekoguard_intake.py <target_path_or_file> [rules.yar]")
        sys.exit(1)
        
    target = sys.argv[1]
    yara_rules = sys.argv[2] if len(sys.argv) > 2 else None
    
    # スキャンの実行
    scan_summary = scan_directory(target, yara_rules)
    
    # レポート生成先を定義
    report_output_dir = os.path.join(os.path.dirname(os.path.abspath(target)), "nekoguard_report")
    if os.path.isfile(target):
        report_output_dir = os.path.join(os.path.dirname(os.path.abspath(target)), "nekoguard_report")
        
    generate_reports(scan_summary, report_output_dir)
