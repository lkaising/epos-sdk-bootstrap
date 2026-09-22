# shellcheck shell=bash
# Stream-specific colors, fixed once at startup.
LOG_ERROR_COLOR='' LOG_RESET=''
if [[ -t 2 && ! ${NO_COLOR+x} ]]; then LOG_ERROR_COLOR=$'\033[31m'; LOG_RESET=$'\033[0m'; fi
log_error() { printf '%s[ERROR]%s %s\n' "$LOG_ERROR_COLOR" "$LOG_RESET" "$*" >&2; }
