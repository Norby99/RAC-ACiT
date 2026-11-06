#!/usr/bin/env bash
# ============================================================
#  LINGUA DEL GIOCO: cambia solo il valore dopo LINGUA=
#    it = italiano     en = inglese     fr = francese
#    es = spagnolo     de = tedesco     nl = olandese
# ============================================================
LINGUA=it


# Da qui in poi non serve modificare nulla.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ESEGUIBILE="$ROOT/game/build-linux/game/RaCACiTRecomp"

if [ ! -x "$ESEGUIBILE" ]; then
    echo "Gioco non trovato: $ESEGUIBILE"
    echo "Va prima compilato con scripts/build_linux.sh"
    exit 1
fi
if [ ! -f "$ROOT/dev/EBOOT.ELF" ]; then
    echo "File non trovato: $ROOT/dev/EBOOT.ELF"
    exit 1
fi

mkdir -p "$ROOT/analysis/run/hdd0" "$ROOT/analysis/run/hdd1"

export PS3_VFS_ROOT="$ROOT/dev/BCES00511"
export PS3_HDD0_ROOT="$ROOT/analysis/run/hdd0"
export PS3_HDD1_ROOT="$ROOT/analysis/run/hdd1"
export RACACIT_LOG_FILE="$ROOT/analysis/run/game.log"
export RACACIT_LANGUAGE="$LINGUA"

cd "$ROOT/analysis/run" || exit 1
exec "$ESEGUIBILE" "$ROOT/dev/EBOOT.ELF"
