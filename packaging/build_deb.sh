#!/usr/bin/env bash
#
# Сборка .deb. Один и тот же скрипт гоняется и локально, и в CI — чтобы то, что
# проверено на машине, совпадало с тем, что уезжает в релиз.
#
#   bash packaging/build_deb.sh 0.1.0
#
# Результат кладётся в dist/ (переопределяется переменной OUT_DIR).
# Архитектура all: внутри только python-код и текстовые файлы, компилировать
# нечего.
set -euo pipefail

# Права внутри пакета не должны зависеть от umask той машины, где идёт сборка:
# локально он один, на раннере другой.
umask 022

if [ $# -ne 1 ]; then
    echo "Использование: $0 ВЕРСИЯ   (например: $0 0.1.0)" >&2
    exit 2
fi

VERSION="$1"
#: Имя пакета и команды в /usr/bin.
PKG="activity-renew"
#: Имя python-модуля. Именно с подчёркиванием: каталог в dist-packages должен
#: называться так же, как модуль, иначе `python3 -m activity_renew` его не
#: найдёт. Дефис в имени модуля недопустим, и однажды это уже стоило
#: неработающего релиза — не возвращайте сюда $PKG.
MODULE="activity_renew"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT_DIR:-$ROOT/dist}"
MAINTAINER="${MAINTAINER:-Pavlenko Evgeniy <pavlenkoevgeniy85@gmail.com>}"

command -v dpkg-deb >/dev/null || { echo "нужен dpkg-deb" >&2; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
chmod 755 "$STAGE"  # mktemp даёт 0700, а корень пакета должен быть обычным

PYDIR="$STAGE/usr/lib/python3/dist-packages/$MODULE"
install -d "$STAGE/DEBIAN" "$PYDIR" "$STAGE/usr/bin" \
    "$STAGE/usr/share/applications" "$STAGE/etc/udev/rules.d" \
    "$STAGE/usr/share/doc/$PKG"

install -m 644 "$ROOT"/activity_renew/*.py "$PYDIR/"
install -m 644 "$ROOT/packaging/activity-renew.desktop" \
    "$STAGE/usr/share/applications/"
# Правило доступа к /dev/uinput едет вместе с пакетом: без него виртуальную
# мышь не видит композитор, и режим uinput молча ничего не делает.
install -m 644 "$ROOT/packaging/99-activity-renew.rules" "$STAGE/etc/udev/rules.d/"
install -m 644 "$ROOT/README.md" "$STAGE/usr/share/doc/$PKG/README.md"
install -m 755 "$ROOT/packaging/launcher" "$STAGE/usr/bin/$PKG"
install -m 755 "$ROOT/packaging/postinst" "$STAGE/DEBIAN/postinst"

# Файл в /etc — значит conffile: dpkg будет спрашивать при расхождении и
# уберёт его при purge.
printf '%s\n' "/etc/udev/rules.d/99-activity-renew.rules" > "$STAGE/DEBIAN/conffiles"

SIZE="$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-tk, python3-dbus, python3-evdev, xdotool
Installed-Size: $SIZE
Maintainer: $MAINTAINER
Description: activity simulation so the session is not considered idle
 Moves the mouse 1 pixel and back when there has been no input for a while.
 It can also ask the GNOME session not to idle through D-Bus.
 The window is built with tkinter.
EOF

mkdir -p "$OUT"
DEB="$OUT/${PKG}_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "$STAGE" "$DEB" >/dev/null
echo "$DEB"
