#!/usr/bin/env bash
# Run the whole study. Needs: ssh access to the machine as "warden", TASMOTA_PASSWORD_WARDEN in the environment
# (from `se`), and this repository checked out locally. Raw logs land in results/<stamp>/.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="$HERE/results/$STAMP"
mkdir -p "$OUT"
ssh warden 'mkdir -p ~/strix-halo-energy' && rsync -a "$HERE/harness/" warden:~/strix-halo-energy/harness/
python3 "$HERE/harness/sample_plug.py" --host 192.168.88.49 --password-env TASMOTA_PASSWORD_WARDEN --out "$OUT/plug.csv" &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null || true' EXIT
ssh warden "set -euo pipefail && cd ~/strix-halo-energy && rm -rf out-$STAMP && python3 harness/warden_study.py --out out-$STAMP --build \$HOME/.local/opt/llama.cpp/${BUILD:-b10970-vulkan} --models-dir \$HOME/models/lifeops --plan harness/${PLAN:-plan.json} --models harness/models.json ${EXTRA:-}"
rsync -a "warden:~/strix-halo-energy/out-$STAMP/" "$OUT/"
sleep 5
kill $SAMPLER 2>/dev/null || true
python3 "$HERE/harness/analyze.py" "$OUT"
echo "done: $OUT"
