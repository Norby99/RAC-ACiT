#!/usr/bin/env bash
# setup_linux.sh: everything the Linux build needs into tools/, at the versions
# the Windows build uses. Safe to run again. System packages: see LINUX.md.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p tools dev

missing=()
for c in git python3 clang clang++ pkg-config; do
    command -v "$c" >/dev/null || missing+=("$c")
done
if [ "${#missing[@]}" -eq 0 ] && ! pkg-config --exists sdl2; then
    missing+=("SDL2 development files")
fi
if [ "${#missing[@]}" -ne 0 ]; then
    echo "Missing: ${missing[*]}. See LINUX.md for the packages." >&2
    exit 1
fi

# pin <dir> <repository> <commit or tag>
pin() {
    [ -d "tools/$1/.git" ] && return 0
    git init -q "tools/$1"
    git -C "tools/$1" remote add origin "https://github.com/$2"
    git -C "tools/$1" -c core.autocrlf=false fetch -q --depth 1 origin "$3"
    git -C "tools/$1" -c core.autocrlf=false checkout -q FETCH_HEAD
    echo "tools/$1: $2 at $3"
}

echo "== Python tools"
[ -x tools/venv/bin/python ] || python3 -m venv tools/venv
tools/venv/bin/python -m pip install -q --disable-pip-version-check \
    cmake==4.4.4 ninja==1.13.2 capstone==5.0.9 construct==2.10.70 \
    pycryptodome==3.24.1 tabulate==0.10.0 tqdm==4.70.1

echo "== Sources"
fresh_runtime=0
[ -d tools/ps3recomp/.git ] || fresh_runtime=1
pin ps3recomp      sp00nznet/ps3recomp         5244db92669b54831c6d3ebb7a96d58c4dbfa6df
pin Vulkan-Headers KhronosGroup/Vulkan-Headers c46850864f4661461b0f6cb9922c058ffea4915e
pin glslang-src    KhronosGroup/glslang        2fbed5e1fb43a1c480fe020e3bb686a31010989a
pin zlib           madler/zlib                 767c4c947852e143f582c85f14cf573411df1b35

# --ignore-whitespace: some of ps3recomp's files mix line endings.
if [ "$fresh_runtime" = 1 ]; then
    git -C tools/ps3recomp apply --ignore-whitespace ../../patches/ps3recomp-0001-racacit-runtime-fixes.patch
    echo "tools/ps3recomp: patched"
fi
echo "Done. Next: scripts/build_linux.sh"
