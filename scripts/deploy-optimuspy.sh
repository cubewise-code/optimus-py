#!/usr/bin/env bash
#
# deploy-optimuspy.sh
#
# Downloads and installs the optimuspy Linux build on a RHEL host.
# Designed for unattended invocation from a TM1 ExecuteCommand TI step,
# which discards stdout/stderr — so EVERYTHING is appended to a log file.
#
# Usage (interactive or from TI):
#   deploy-optimuspy.sh [release-tag]
#
# Environment overrides (all optional):
#   GITHUB_REPO    owner/repo                 default: cubewise-code/optimus-py
#   RELEASE_TAG    GitHub release tag         default: latest
#   INSTALL_DIR    where to unpack            default: /opt/optimuspy
#   SYMLINK_PATH   symlink to the binary      default: /usr/local/bin/optimuspy
#                  (set to empty string to skip symlink creation)
#   LOG_FILE       log path                   default: /var/log/optimuspy-deploy.log
#                                                       (falls back to ~/optimuspy-deploy.log)
#   LOCAL_TARBALL  path to a pre-staged       default: <unset> (download from GitHub)
#                  optimuspy-linux.tar.gz —
#                  use this for air-gapped hosts.
#
# The user running this needs write access to INSTALL_DIR's parent and
# (if SYMLINK_PATH is set) to the symlink's parent directory.
#
# Exit codes: 0 success, non-zero on any failure (logged with line + command).

set -euo pipefail
umask 022

# ---------- config ----------
GITHUB_REPO="${GITHUB_REPO:-cubewise-code/optimus-py}"
RELEASE_TAG="${RELEASE_TAG:-${1:-latest}}"
INSTALL_DIR="${INSTALL_DIR:-/opt/optimuspy}"
SYMLINK_PATH="${SYMLINK_PATH-/usr/local/bin/optimuspy}"
LOCAL_TARBALL="${LOCAL_TARBALL:-}"
ASSET_NAME="optimuspy-linux.tar.gz"

# ---------- logging ----------
if [[ -z "${LOG_FILE:-}" ]]; then
    if touch /var/log/optimuspy-deploy.log 2>/dev/null; then
        LOG_FILE="/var/log/optimuspy-deploy.log"
    else
        LOG_FILE="$HOME/optimuspy-deploy.log"
    fi
fi
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
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
log "user=$(id -un)  host=$(hostname)  pwd=$(pwd)"
log "GITHUB_REPO=$GITHUB_REPO"
log "RELEASE_TAG=$RELEASE_TAG"
log "INSTALL_DIR=$INSTALL_DIR"
log "SYMLINK_PATH=${SYMLINK_PATH:-<skipped>}"
log "LOCAL_TARBALL=${LOCAL_TARBALL:-<none, will download>}"
log "LOG_FILE=$LOG_FILE"

# ---------- prereqs ----------
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"; }
need_cmd tar
need_cmd mktemp
need_cmd mv
need_cmd ln
[[ -n "$LOCAL_TARBALL" ]] || need_cmd curl

# ---------- workspace (same FS as INSTALL_DIR for atomic mv) ----------
PARENT_DIR="$(dirname "$INSTALL_DIR")"
mkdir -p "$PARENT_DIR" || fail "cannot create parent dir: $PARENT_DIR"
WORK_DIR="$(mktemp -d -p "$PARENT_DIR" .optimuspy-deploy.XXXXXX)"
log "work dir: $WORK_DIR"

cleanup() {
    [[ -d "$WORK_DIR" ]] && rm -rf "$WORK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

# ---------- obtain tarball ----------
TARBALL="$WORK_DIR/$ASSET_NAME"

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

TARBALL_SIZE="$(stat -c %s "$TARBALL" 2>/dev/null || echo unknown)"
log "tarball size: $TARBALL_SIZE bytes"
[[ "$TARBALL_SIZE" != "0" ]] || fail "tarball is empty"

# ---------- extract ----------
log "extracting tarball"
tar -xzf "$TARBALL" -C "$WORK_DIR"
EXTRACTED_DIR="$WORK_DIR/optimuspy-linux"
[[ -d "$EXTRACTED_DIR" ]] || fail "expected directory $EXTRACTED_DIR not in tarball"
[[ -f "$EXTRACTED_DIR/optimuspy" ]] || fail "binary $EXTRACTED_DIR/optimuspy missing"
chmod +x "$EXTRACTED_DIR/optimuspy"

# ---------- smoke test (loader sanity, before touching install dir) ----------
log "smoke test: invoke binary"
SMOKE_OUT="$("$EXTRACTED_DIR/optimuspy" --help 2>&1 || true)"
log "smoke test output (first 40 lines):"
printf '%s\n' "$SMOKE_OUT" | head -n 40
if printf '%s' "$SMOKE_OUT" | grep -q "error while loading shared libraries"; then
    fail "binary failed to load shared libraries — aborting deploy"
fi
log "smoke test passed (no loader errors)"

# ---------- install (atomic-ish: backup old, mv new into place) ----------
BACKUP=""
if [[ -d "$INSTALL_DIR" ]]; then
    BACKUP="${INSTALL_DIR}.bak.$(date -u +%Y%m%d-%H%M%S)"
    log "backing up existing install: $INSTALL_DIR -> $BACKUP"
    mv "$INSTALL_DIR" "$BACKUP" || fail "backup move failed"
fi

log "installing into $INSTALL_DIR"
if ! mv "$EXTRACTED_DIR" "$INSTALL_DIR"; then
    log "install move failed; attempting rollback"
    if [[ -n "$BACKUP" && -d "$BACKUP" ]]; then
        mv "$BACKUP" "$INSTALL_DIR" \
            && log "rollback restored previous install" \
            || log "rollback FAILED — manual recovery required from $BACKUP"
    fi
    fail "install move failed"
fi

# ---------- symlink ----------
if [[ -n "$SYMLINK_PATH" ]]; then
    SYM_PARENT="$(dirname "$SYMLINK_PATH")"
    if [[ ! -d "$SYM_PARENT" ]]; then
        log "warn: symlink parent $SYM_PARENT does not exist; skipping symlink"
    elif ln -sfn "$INSTALL_DIR/optimuspy" "$SYMLINK_PATH"; then
        log "symlink: $SYMLINK_PATH -> $INSTALL_DIR/optimuspy"
    else
        log "warn: failed to create symlink at $SYMLINK_PATH (continuing)"
    fi
fi

# ---------- post-install verify ----------
log "post-install verify"
VERIFY_OUT="$("$INSTALL_DIR/optimuspy" --help 2>&1 || true)"
if printf '%s' "$VERIFY_OUT" | grep -q "error while loading shared libraries"; then
    fail "post-install verify FAILED — backup retained at $BACKUP"
fi
log "post-install verify passed"

if [[ -n "$BACKUP" ]]; then
    log "previous install retained at $BACKUP — remove manually when satisfied"
fi

log "deploy complete: $INSTALL_DIR"
log "=================================================================="
exit 0
