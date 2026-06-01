#!/usr/bin/env bash
# Run Moodle cron once as www-data (processes adhoc tasks, e.g. async course restore).
# From repo root: bash scripts/moodle-cron-once.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -u www-data moodle /usr/local/bin/php /var/www/html/moodle/admin/cli/cron.php
echo "Cron finished. If a restore was stuck on 'Process pending', open the course restore page again."
echo "Inspect tasks: Site administration → Server → Tasks → Adhoc tasks."
echo "If it failed: check task logs / failures and PHP logs; tail /var/www/moodledata/moodle-cron.log in the moodle container."
