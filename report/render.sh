#!/usr/bin/env bash
# render.sh <report dir>: PDF of report.html and PNG share cards, through the Playwright of a sibling repo.
set -euo pipefail
DIR="$(realpath "$1")"; MODULES=""
for r in sign.abundera.ai abundera.ai qr.abundera.ai; do
  [ -d "$HOME/projects/$r/node_modules/playwright" ] && MODULES="$HOME/projects/$r/node_modules" && break; done
[ -n "$MODULES" ] || { echo "no sibling node_modules with playwright" >&2; exit 1; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
ln -s "$MODULES" "$TMP/node_modules"
cat > "$TMP/r.mjs" <<'J'
import { chromium } from "playwright";
const dir = process.argv[2];
const b = await chromium.launch();
let p = await b.newPage({ viewport: { width: 900, height: 1200 } });
await p.goto(`file://${dir}/report.html`);
await p.pdf({ path: `${dir}/report.pdf`, format: "A4", printBackground: true, margin: { top: "14mm", bottom: "14mm", left: "12mm", right: "12mm" } });
for (const n of ["share-energy", "share-speed"]) {
  p = await b.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 2 });
  await p.goto(`file://${dir}/${n}.html`);
  await p.screenshot({ path: `${dir}/${n}.png` });
}
await b.close();
J
(cd "$TMP" && node r.mjs "$DIR")
ls -la "$DIR"/report.pdf "$DIR"/share-*.png
