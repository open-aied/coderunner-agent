# Run Moodle cron once as www-data (processes adhoc tasks, e.g. async course restore).
# From repo root: .\scripts\moodle-cron-once.ps1
# Requires Docker and (recommended) a .env file if your compose file references it.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose exec -u www-data moodle /usr/local/bin/php /var/www/html/moodle/admin/cli/cron.php
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose exec failed (exit $LASTEXITCODE). Is Docker running and the stack up?"
    exit $LASTEXITCODE
}
Write-Host "Cron finished. If a restore was stuck on 'Process pending', open the course restore page again."
Write-Host "Inspect tasks: Site administration -> Server -> Tasks -> Adhoc tasks."
Write-Host "If it failed: check the same area for failed / task logs and PHP error logs; tail /var/www/moodledata/moodle-cron.log in the moodle container."
