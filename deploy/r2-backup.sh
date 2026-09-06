#!/usr/bin/env bash
# Snapshot the user home volume to R2 (S3-compatible) and restore it back.
# Credentials come from the environment (.env, never committed):
#   R2_ENDPOINT, R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
# Requires: docker, aws cli (v2) on the host.
#
#   ./deploy/r2-backup.sh backup            # yourdaas-home-<utc>.tgz -> R2
#   ./deploy/r2-backup.sh restore <key>     # R2 key -> yourdaas-home (volume must exist)
set -uo pipefail

VOLUME="${VOLUME:-yourdaas-home}"

need() {
  for v in R2_ENDPOINT R2_BUCKET R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY; do
    if [[ -z "${!v:-}" ]]; then echo "missing env: $v" >&2; exit 1; fi
  done
  command -v docker >/dev/null || { echo "missing: docker" >&2; exit 1; }
  command -v aws >/dev/null || { echo "missing: aws cli" >&2; exit 1; }
}

r2() {
  AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
    aws --endpoint-url "$R2_ENDPOINT" s3 "$@"
}

cmd="${1:-}"; key="${2:-}"

case "$cmd" in
  backup)
    need
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    file="yourdaas-home-${stamp}.tgz"
    tmp="$(mktemp -d)" && trap 'rm -rf "$tmp"' EXIT
    docker run --rm -v "${VOLUME}:/data:ro" -v "${tmp}:/out" \
      debian:bookworm-slim tar czf "/out/${file}" -C /data .
    r2 cp "${tmp}/${file}" "s3://${R2_BUCKET}/backups/${file}"
    echo "backed up: backups/${file}"
    ;;
  restore)
    need
    [[ -n "$key" ]] || { echo "usage: $0 restore <r2-key>" >&2; exit 1; }
    tmp="$(mktemp -d)" && trap 'rm -rf "$tmp"' EXIT
    r2 cp "s3://${R2_BUCKET}/${key}" "${tmp}/restore.tgz"
    docker volume inspect "$VOLUME" >/dev/null 2>&1 || docker volume create "$VOLUME" >/dev/null
    docker run --rm -v "${VOLUME}:/data" -v "${tmp}:/in" \
      debian:bookworm-slim tar xzf /in/restore.tgz -C /data
    echo "restored into volume: $VOLUME"
    ;;
  *)
    echo "usage: $0 {backup|restore <r2-key>}" >&2; exit 1
    ;;
esac
