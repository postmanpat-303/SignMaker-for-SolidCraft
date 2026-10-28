#!/usr/bin/env bash
# Build a standalone Sign Maker bundle for the OS this script is running on.
# Used by the Release workflow. Does not publish anything.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="$ROOT/packaging/out"
rm -rf "$OUT" "$ROOT/build" "$ROOT/dist"
mkdir -p "$OUT"

uname_s="$(uname -s)"
arch="$(uname -m)"
case "$uname_s" in
  Darwin) kind=macos ;;
  Linux) kind=linux ;;
  MINGW*|MSYS*|CYGWIN*) kind=windows ;;
  *)
    echo "Unsupported OS: $uname_s" >&2
    exit 1
    ;;
esac

if [[ "$kind" == "macos" ]]; then
  app_name="Sign Maker"
else
  app_name="SignMaker"
fi

# PyInstaller --add-data uses ; on Windows and : everywhere else.
if [[ "$kind" == "windows" ]]; then
  data_sep=";"
else
  data_sep=":"
fi
args=(
  --noconfirm
  --clean
  --windowed
  --name "$app_name"
  --hidden-import signcore
  --hidden-import PIL._tkinter_finder
  --hidden-import sv_ttk
  --collect-data sv_ttk
  --collect-submodules fontTools.ttLib
  --collect-submodules PIL
  --add-data "assets${data_sep}assets"
)
if [[ "$kind" == "windows" ]]; then
  # Per-monitor DPI aware manifest: sharp text at 125 % / 150 % / 175 % display scaling.
  args+=(--icon "assets/icon.ico" --manifest "packaging/windows/signmaker.manifest")
elif [[ "$kind" == "macos" ]]; then
  # universal2 needs a universal2 Python. GitHub macos-latest is Apple silicon
  # and its Python is arm64 only, so the bundle matches the runner.
  args+=(--icon "assets/icon.icns" --osx-bundle-identifier com.postmanpat.signmaker)
fi

python -m PyInstaller "${args[@]}" SignMaker.pyw

readme_txt() {
  cat << EOF
Sign Maker for SolidCraft
Author: Del (postmanpat)

This is an unofficial community add-on. It is not affiliated with or
endorsed by the SolidCraft maintainers.
SolidCraft itself is not inside this download. Install a build that
includes solidcraft-cli from:
https://github.com/tangency-labs/solidcraft/releases

EOF
}

if [[ "$kind" == "windows" ]]; then
  {
    readme_txt
    echo "Unzip this folder and run SignMaker.exe."
    echo "Leave the _internal folder next to SignMaker.exe."
    echo "This build is Windows x64."
    echo "Prefer an installer? Use SignMaker-<version>-setup-x64.exe from the same release."
  } > "$ROOT/dist/SignMaker/README.txt"
  cp "$ROOT/LICENSE" "$ROOT/dist/SignMaker/LICENSE.txt"
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "Compress-Archive -Path 'dist/SignMaker/*' -DestinationPath 'packaging/out/SignMaker-windows-x64.zip' -Force"
  else
    (cd "$ROOT/dist/SignMaker" && tar -a -cf "$OUT/SignMaker-windows-x64.zip" .)
  fi
  # Setup exe (NSIS, packaging/windows/signmaker.nsi). Version comes from
  # $VERSION, else the v* tag being built, else 0.0.0.
  version="${VERSION:-}"
  if [[ -z "$version" && "${GITHUB_REF_TYPE:-}" == "tag" ]]; then
    version="${GITHUB_REF_NAME#v}"
  fi
  version="${version:-0.0.0}"
  IFS=. read -r v1 v2 v3 v4 <<< "${version%%-*}"
  viversion="${v1:-0}.${v2:-0}.${v3:-0}.${v4:-0}"
  makensis_bin="$(command -v makensis || true)"
  if [[ -z "$makensis_bin" && -x "/c/Program Files (x86)/NSIS/makensis.exe" ]]; then
    makensis_bin="/c/Program Files (x86)/NSIS/makensis.exe"
  fi
  if [[ -n "$makensis_bin" ]]; then
    # MSYS would rewrite /DVERSION=... as a path; NSIS also accepts -D.
    MSYS2_ARG_CONV_EXCL="*" "$makensis_bin" -V3 \
      "-DVERSION=$version" "-DVIVERSION=$viversion" \
      "-DPKGDIR=..\\..\\dist\\SignMaker" \
      "-DOUTFILE=..\\out\\SignMaker-${version}-setup-x64.exe" \
      "packaging/windows/signmaker.nsi"
  else
    echo "makensis not found: skipping the setup exe" >&2
  fi
elif [[ "$kind" == "macos" ]]; then
  stage="$ROOT/dist/macos-stage"
  rm -rf "$stage"
  mkdir -p "$stage"
  cp -R "$ROOT/dist/Sign Maker.app" "$stage/"
  {
    readme_txt
    echo "Open \"Sign Maker.app\"."
    echo "The app is unsigned. The first time, right-click it and choose Open."
    echo "This build is ${arch}, not a universal2 binary."
    echo "Intel Macs can run the source copy with run.command."
  } > "$stage/README.txt"
  # ditto keeps the app bundle structure, including symlinks.
  ditto -c -k --keepParent "$stage" "$OUT/SignMaker-macos-${arch}.zip"
else
  {
    readme_txt
    echo "tar -xzf SignMaker-linux-${arch}.tar.gz"
    echo "./SignMaker/SignMaker"
    echo "This build is Linux ${arch}, made on Ubuntu."
    echo "icon.png and sign-maker.desktop are in this folder."
    echo "To pin a launcher, copy sign-maker.desktop to ~/.local/share/applications"
    echo "and set Exec and Icon to the full paths of SignMaker and icon.png."
  } > "$ROOT/dist/SignMaker/README.txt"
  cp "$ROOT/assets/icon.png" "$ROOT/dist/SignMaker/icon.png"
  cp "$ROOT/packaging/sign-maker.desktop" "$ROOT/dist/SignMaker/sign-maker.desktop"
  tar -C "$ROOT/dist" -czf "$OUT/SignMaker-linux-${arch}.tar.gz" SignMaker
fi

echo "Wrote:"
ls -lh "$OUT"
