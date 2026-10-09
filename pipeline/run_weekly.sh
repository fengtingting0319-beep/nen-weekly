#!/usr/bin/env bash
# NEN weekly report - unattended weekly runner (local cron AND GitHub Actions).
# Usage: ./run_weekly.sh [START END]   (default: last 7 days ending yesterday)
# Output: HTML + Markdown summary + landing page index.html in $NEN_WEEKLY_OUT (default: ../site)
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -ge 2 ]; then
  START="$1"; END="$2"
else
  END=$(date -d "yesterday" +%F 2>/dev/null || date -v-1d +%F)
  START=$(date -d "8 days ago" +%F 2>/dev/null || date -v-8d +%F)
fi
echo "[run_weekly] window ${START} .. ${END}"

OUTDIR="${NEN_WEEKLY_OUT:-../site}"
mkdir -p "$OUTDIR"

python 01_retrieve.py "$START" "$END" raw
python 02_process.py raw processed.json
python 03_build_html.py processed.json raw "$OUTDIR/NEN_weekly_${END}.html"
python 04_summary_md.py processed.json raw "$OUTDIR/NEN_weekly_${END}_summary.md"
python 05_build_index.py "$OUTDIR"

# per-issue data archive for traceability (best-effort; never fails the run)
ROOT="$(cd .. && pwd)"
mkdir -p "$ROOT/archive" 2>/dev/null || true
cp processed.json "$ROOT/archive/${END}_processed.json" 2>/dev/null || true
cp raw/query_log.json "$ROOT/archive/${END}_query_log.json" 2>/dev/null || true

echo "[run_weekly] done -> $OUTDIR/NEN_weekly_${END}.html"
echo "[run_weekly] NOTE: 本周看点/精读/中文要点/临床意义/课题借鉴 为编辑内容，"
echo "            无人值守运行发布基础版（自动摘要 + 待补充标注）后，"
echo "            请在 Biomni 会话中让编辑基于当期摘要补充 content*.py 并重新渲染。"
