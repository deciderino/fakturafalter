#!/bin/sh
# Alle Messungen in einen Ordner: tools/messen.sh <name>  (Benchmark mit Sets, Seeds 1..5 mit 100 Drucken, Kopffeld)
set -e
W=$(cd "$(dirname "$0")/.." && pwd)
PY=${PY:-python3}
SETS=${SETS:-"$W/beispiele/sets/fiktiva $W/beispiele/sets/kommentarzeilen"}
O=${MESSUNGEN:-$W/tools/messungen}/$1
mkdir -p "$O"
export PYTHONPATH=$W/src QT_QPA_PLATFORM=offscreen
cd "$W"
$PY tools/benchmark.py --set $SETS --md "$O/benchmark.md" --json "$O/benchmark.json" --max-fehl 1 > /dev/null &
for s in 1 2 3 4 5; do
  $PY tools/benchmark.py --verfahren assistent --generator 100 --seed $s --set --md "$O/seed$s.md" --json "$O/seed$s.json" --max-fehl 1 > /dev/null &
done
$PY tools/kopffeld_messung.py --md "$O/kopffeld.md" --json "$O/kopffeld.json" > /dev/null &
wait
echo fertig "$O"
