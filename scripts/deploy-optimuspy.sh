#!/usr/bin/env bash
#
# deploy-optimuspy.sh
#
# Downloads and installs the optimuspy Linux build INTO THE SCRIPT'S OWN
# DIRECTORY. Designed to run as a non-root TM1 service account from a
# TM1 ExecuteCommand TI step. ExecuteCommand discards stdout/stderr, so
# everything is appended (timestamped) to a log file next to the script.
#
# After a successful deploy the directory looks like:
#   <INSTALL_DIR>/
#   |-- deploy-optimuspy.sh   (this script — left alone)
#   |-- config.ini            (user-managed — left alone)
#   |-- optimuspy             (the binary, +x)
#   |-- _internal/            (PyInstaller bundled libs + data)
#   |-- optimuspy-deploy.log  (this script's log)
#   `-- *.bak.<ts>            (previous binary + _internal, kept for rollback)
#
# Only `optimuspy` and `_internal/` are ever replaced. Anything else in
# the directory (config.ini, logs, user files) is untouched.
#
# Usage:
#   chmod +x deploy-optimuspy.sh        # one-time, after first download
#   ./deploy-optimuspy.sh [release-tag]
#
# Environment overrides (all optional):
#   GITHUB_REPO    owner/repo                 default: cubewise-code/optimus-py
#   RELEASE_TAG    GitHub release tag         default: latest
#   INSTALL_DIR    where to install           default: this script's directory
#   LOG_FILE       log file path              default: $INSTALL_DIR/optimuspy-deploy.log
#   LOCAL_TARBALL  path to a pre-staged       default: <unset> (download from GitHub)
#                  optimuspy-linux.tar.gz —
#                  use this for air-gapped hosts.
#   KEEP_BACKUPS   how many old .bak.* sets   default: 3
#                  to keep (older ones pruned).

set -euo pipefail
umask 022

# ---------- locate self ----------
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"

# ---------- config ----------
GITHUB_REPO="${GITHUB_REPO:-cubewise-code/optimus-py}"
RELEASE_TAG="${RELEASE_TAG:-${1:-latest}}"
INSTALL_DIR="${INSTALL_DIR:-$SCRIPT_DIR}"
LOCAL_TARBALL="${LOCAL_TARBALL:-}"
KEEP_BACKUPS="${KEEP_BACKUPS:-3}"
ASSET_NAME="optimuspy-linux.tar.gz"
MANAGED_ITEMS=(optimuspy _internal)

# ---------- logging ----------
LOG_FILE="${LOG_FILE:-$INSTALL_DIR/optimuspy-deploy.log}"
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
touch "$LOG_FILE" 2>/dev/null || {
    echo "FATAL: cannot write log file $LOG_FILE" >&2
    exit 1
}
exec >>"$LOG_FILE" 2>&1

ts()   { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log()  { printf '[%s] %s\n' "$(ts)" "$*"; }
fail() { log "ERROR: $*"; exit 1; }

on_error() {
    local rc=$?
    local line=${BASH_LINENO[0]:-?}
    log "FATAL: command failed (exit=$rc) at line $line: ${BASH_COMMAND}"
    exit "$rc"
}
trap on_error ERR

log "=================================================================="
log "deploy-optimuspy.sh starting"
log "user=$(id -un)  host=$(hostname)"
log "SCRIPT_PATH=$SCRIPT_PATH"
log "INSTALL_DIR=$INSTALL_DIR"
log "GITHUB_REPO=$GITHUB_REPO"
log "RELEASE_TAG=$RELEASE_TAG"
log "LOCAL_TARBALL=${LOCAL_TARBALL:-<none, will download>}"
log "KEEP_BACKUPS=$KEEP_BACKUPS"
log "LOG_FILE=$LOG_FILE"

# ---------- prereqs ----------
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"; }
need_cmd tar
need_cmd mktemp
need_cmd mv
need_cmd readlink
[[ -n "$LOCAL_TARBALL" ]] || need_cmd curl

# Ensure we can write to the install dir
[[ -d "$INSTALL_DIR" ]] || fail "INSTALL_DIR does not exist: $INSTALL_DIR"
[[ -w "$INSTALL_DIR" ]] || fail "INSTALL_DIR is not writable by $(id -un): $INSTALL_DIR"

# ---------- workspace (same FS as INSTALL_DIR for atomic rename) ----------
STAGING="$(mktemp -d -p "$INSTALL_DIR" .deploy-staging.XXXXXX)"
log "staging dir: $STAGING"

cleanup() {
    [[ -d "$STAGING" ]] && rm -rf "$STAGING" 2>/dev/null || true
}
trap cleanup EXIT

# ---------- obtain tarball ----------
TARBALL="$STAGING/$ASSET_NAME"

if [[ -n "$LOCAL_TARBALL" ]]; then
    [[ -f "$LOCAL_TARBALL" ]] || fail "LOCAL_TARBALL not found: $LOCAL_TARBALL"
    log "using local tarball: $LOCAL_TARBALL"
    cp "$LOCAL_TARBALL" "$TARBALL"
else
    if [[ "$RELEASE_TAG" == "latest" ]]; then
        URL="https://github.com/${GITHUB_REPO}/releases/latest/download/${ASSET_NAME}"
    else
        URL="https://github.com/${GITHUB_REPO}/releases/download/${RELEASE_TAG}/${ASSET_NAME}"
    fi
    log "downloading: $URL"
    curl -fSL --retry 3 --retry-delay 5 --connect-timeout 30 \
         -o "$TARBALL" "$URL" \
        || fail "download failed from $URL"
fi

TARBALL_SIZE="$(stat -c %s "$TARBALL" 2>/dev/null || echo 0)"
log "tarball size: $TARBALL_SIZE bytes"
[[ "$TARBALL_SIZE" -gt 0 ]] || fail "tarball is empty"

# ---------- extract ----------
log "extracting tarball"
tar -xzf "$TARBALL" -C "$STAGING"
EXTRACTED_DIR="$STAGING/optimuspy-linux"
[[ -d "$EXTRACTED_DIR" ]] || fail "expected directory $EXTRACTED_DIR not in tarball"
[[ -f "$EXTRACTED_DIR/optimuspy" ]] || fail "binary $EXTRACTED_DIR/optimuspy missing"
[[ -d "$EXTRACTED_DIR/_internal" ]] || fail "directory $EXTRACTED_DIR/_internal missing"
chmod +x "$EXTRACTED_DIR/optimuspy"

# ---------- smoke test (loader sanity, before touching install dir) ----------
log "smoke test: invoke staged binary"
SMOKE_OUT="$("$EXTRACTED_DIR/optimuspy" --help 2>&1 || true)"
log "smoke test output (first 40 lines):"
printf '%s\n' "$SMOKE_OUT" | head -n 40
if printf '%s' "$SMOKE_OUT" | grep -q "error while loading shared libraries"; then
    fail "binary failed to load shared libraries — aborting deploy"
fi
log "smoke test passed (no loader errors)"

# ---------- install: only replace MANAGED_ITEMS, leave everything else ----------
TS="$(date -u +%Y%m%d-%H%M%S)"
declare -a BACKED_UP=()

log "installing managed items into $INSTALL_DIR"
for item in "${MANAGED_ITEMS[@]}"; do
    src="$EXTRACTED_DIR/$item"
    dst="$INSTALL_DIR/$item"
    bak="${dst}.bak.${TS}"

    if [[ -e "$dst" ]]; then
        log "  backup: $dst -> $bak"
        if ! mv "$dst" "$bak"; then
            log "  ERROR: backup failed for $dst — rolling back"
            for done_item in "${BACKED_UP[@]}"; do
                done_dst="$INSTALL_DIR/$done_item"
                done_bak="${done_dst}.bak.${TS}"
                [[ -e "$done_dst" ]] && rm -rf "$done_dst"
                [[ -e "$done_bak" ]] && mv "$done_bak" "$done_dst"
            done
            fail "deploy aborted; previous install restored"
        fi
        BACKED_UP+=("$item")
    fi

    log "  install: $src -> $dst"
    if ! mv "$src" "$dst"; then
        log "  ERROR: install move failed for $src — rolling back"
        for done_item in "${BACKED_UP[@]}"; do
            done_dst="$INSTALL_DIR/$done_item"
            done_bak="${done_dst}.bak.${TS}"
            [[ -e "$done_dst" ]] && rm -rf "$done_dst"
            [[ -e "$done_bak" ]] && mv "$done_bak" "$done_dst"
        done
        fail "deploy aborted; previous install restored"
    fi
done

chmod +x "$INSTALL_DIR/optimuspy"

# ---------- post-install verify ----------
log "post-install verify"
VERIFY_OUT="$("$INSTALL_DIR/optimuspy" --help 2>&1 || true)"
if printf '%s' "$VERIFY_OUT" | grep -q "error while loading shared libraries"; then
    fail "post-install verify FAILED — manual recovery from .bak.${TS} files required"
fi
log "post-install verify passed"

# ---------- prune old backups ----------
if [[ "$KEEP_BACKUPS" =~ ^[0-9]+$ ]] && [[ "$KEEP_BACKUPS" -gt 0 ]]; then
    for item in "${MANAGED_ITEMS[@]}"; do
        # newest first; keep first N, delete the rest
        mapfile -t old_baks < <(
            ls -1dt "$INSTALL_DIR/${item}.bak."* 2>/dev/null | tail -n +"$((KEEP_BACKUPS + 1))"
        )
        for old in "${old_baks[@]}"; do
            log "pruning old backup: $old"
            rm -rf "$old" || log "  warn: failed to remove $old"
        done
    done
fi

log "deploy complete: $INSTALL_DIR"
log "=================================================================="
exit 0
