#!/bin/sh
set -e

run_alembic() {
    if output="$("$@" 2>&1)"; then
        [ -z "$output" ] || printf '%s\n' "$output"
        return 0
    else
        status=$?
        printf '%s\n' "$output" >&2
        case "$output" in
            *"Can't locate revision identified by"*)
                echo "WARNING: Ignoring missing Alembic revision and continuing." >&2
                return 0
                ;;
            *)
                return "$status"
                ;;
        esac
    fi
}

echo "Generating new migrations from current models..."
run_alembic alembic revision --autogenerate -m "auto"

echo "Applying generated migrations..."
run_alembic alembic upgrade head

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-80}"
