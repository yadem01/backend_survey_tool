#!/bin/sh
# docker-entrypoint.sh

set -e

echo "Warte auf PostgreSQL..."

echo "Führe Datenbank-Migrationen aus..."
alembic upgrade head

echo "Datenbank-Migrationen abgeschlossen."

exec "$@"