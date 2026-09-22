# shellcheck shell=bash
# Structured records, locking and filesystem operations stay in one Python process.
run_bootstrap() {
  /usr/bin/python3 -B "$PROJECT_DIR/lib/bootstrap.py" "$@"
}
