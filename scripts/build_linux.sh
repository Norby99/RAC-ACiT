#!/usr/bin/env bash
# build_linux.sh [jobs]: lift dev/EBOOT.ELF and compile game/build-linux/game/RaCACiTRecomp.
# The default of 6 jobs wants about 32 GB of RAM; pass a lower number on less.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
JOBS="${1:-6}"
export PATH="$ROOT/tools/venv/bin:$PATH"

PY="$ROOT/tools/venv/bin/python -I" SKIP_DESKTOP=1 bash scripts/pipeline.sh

cmake -S linux -B game/build-linux -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
    -DPython3_EXECUTABLE="$ROOT/tools/venv/bin/python"
cmake --build game/build-linux -j"$JOBS"
echo "Done: game/build-linux/game/RaCACiTRecomp. Start it with ./run.sh"
