#!/bin/sh
set -eu

[ "$#" -eq 2 ] || {
    echo "usage: backup.sh DATA_DIR BACKUP_DIR" >&2
    exit 2
}

[ -d "$1" ] || {
    echo "data directory does not exist" >&2
    exit 1
}

data_dir=$(realpath "$1")
mkdir -p "$2"
backup_dir=$(realpath "$2")

case "$backup_dir/" in
    "$data_dir/"*)
        echo "backup directory must be outside data directory" >&2
        exit 1
        ;;
esac

stamp=$(date -u +%Y%m%dT%H%M%SZ)
archive="$backup_dir/annotation-desk-$stamp.tar.gz"
temporary=$(mktemp "$backup_dir/.annotation-desk-backup.XXXXXX")
trap 'rm -f "$temporary"' EXIT HUP INT TERM

tar -C "$data_dir" -czf "$temporary" .
mv "$temporary" "$archive"
trap - EXIT HUP INT TERM
printf '%s\n' "$archive"
