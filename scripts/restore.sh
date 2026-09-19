#!/bin/sh
set -eu

[ "$#" -eq 2 ] || {
    echo "usage: restore.sh ARCHIVE DATA_DIR" >&2
    exit 2
}

[ -f "$1" ] || {
    echo "backup archive does not exist" >&2
    exit 1
}

archive=$(realpath "$1")
target_parent=$(realpath "$(dirname "$2")")
target="$target_parent/$(basename "$2")"

if [ -d "$target" ] && [ "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    echo "restore target must be empty" >&2
    exit 1
fi

members=$(mktemp "$target_parent/.annotation-desk-members.XXXXXX")
temporary=$(mktemp -d "$target_parent/.annotation-desk-restore.XXXXXX")
trap 'rm -f "$members"; rm -rf "$temporary"' EXIT HUP INT TERM

tar -tzf "$archive" > "$members"
while IFS= read -r member; do
    clean=${member#./}
    case "/$clean/" in
        */../*)
            echo "archive contains unsafe path" >&2
            exit 1
            ;;
    esac
    case "$member" in
        /*)
            echo "archive contains absolute path" >&2
            exit 1
            ;;
    esac
done < "$members"

tar -C "$temporary" -xzf "$archive"
[ -f "$temporary/app.sqlite3" ] || {
    echo "backup does not contain app.sqlite3" >&2
    exit 1
}

if [ -d "$target" ]; then
    rmdir "$target"
fi
mv "$temporary" "$target"
rm -f "$members"
trap - EXIT HUP INT TERM
printf '%s\n' "$target"
