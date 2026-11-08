#!/bin/bash
set -e

FILES=$(find qui qubes_config \( -name '*.py' -o -name '*.glade' \) -not -path '*/tests/*' | sort)

# xgettext rejects the "coding: utf8" spelling used in file headers,
# so extract from a temporary copy with it normalized to "utf-8"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cp --parents $FILES "$TMP"
sed -i 's/coding: utf8 /coding: utf-8 /' $(cd "$TMP" && find . -name '*.py' -printf "$TMP/%P\n")

(cd "$TMP" && xgettext -d desktop-linux-manager -o "$OLDPWD/locale/desktop-linux-manager.pot" \
    --from-code=UTF-8 --add-comments=TRANSLATORS $FILES)

find locale/* -maxdepth 2 -mindepth 2 -type f -iname '*.po' -exec msgmerge --update {} locale/desktop-linux-manager.pot \;
