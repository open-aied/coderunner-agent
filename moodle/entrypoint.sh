#!/usr/bin/env bash
set -euo pipefail

MOODLE_DIR="/var/www/html/moodle"
MOODLE_DATA="/var/www/moodledata"
CONFIG_PHP="${MOODLE_DIR}/config.php"

WWWROOT="${MOODLE_WWWROOT:-http://localhost}"
SSL_PROXY="${MOODLE_SSL_PROXY:-false}"
AGENT_URL="${CODERUNNER_AGENT_URL:-http://host.docker.internal:8001}"
MOODLE_TIMEZONE_VALUE="${MOODLE_TIMEZONE:-Asia/Tokyo}"

configure_php_timezone() {
    cat > /usr/local/etc/php/conf.d/zz-moodle-timezone.ini << INIEOF
date.timezone = ${MOODLE_TIMEZONE_VALUE}
INIEOF
    echo "[moodle] PHP timezone configured: ${MOODLE_TIMEZONE_VALUE}"
}

configure_moodle_timezone() {
    if [ ! -f "${MOODLE_DIR}/admin/cli/cfg.php" ]; then
        return 0
    fi
    php "${MOODLE_DIR}/admin/cli/cfg.php" --name=timezone --set="${MOODLE_TIMEZONE_VALUE}" >/dev/null
    echo "[moodle] Moodle site timezone configured: ${MOODLE_TIMEZONE_VALUE}"
}

configure_session_cookie() {
    # Moodle's session cookie name is 'MoodleSession' + $CFG->sessioncookie.
    # Setting a per-deployment suffix prevents cookie collisions when multiple
    # PHP/Moodle apps share the same hostname (e.g. behind a reverse proxy).
    [ -f "${MOODLE_DIR}/admin/cli/cfg.php" ] || return 0
    local desired="${MOODLE_SESSION_COOKIE_SUFFIX:-${MOODLE_COOKIE_PREFIX:-cra}}"
    [ -z "${desired}" ] && return 0
    local current
    current=$(php "${MOODLE_DIR}/admin/cli/cfg.php" --name=sessioncookie 2>/dev/null || true)
    if [ "${current}" != "${desired}" ]; then
        php "${MOODLE_DIR}/admin/cli/cfg.php" --name=sessioncookie --set="${desired}" >/dev/null 2>&1 || true
        php "${MOODLE_DIR}/admin/cli/purge_caches.php" >/dev/null 2>&1 || true
        local after
        after=$(php "${MOODLE_DIR}/admin/cli/cfg.php" --name=sessioncookie 2>/dev/null || true)
        if [ "${after}" = "${desired}" ]; then
            echo "[moodle] sessioncookie suffix set to '${desired}' (was '${current:-<unset>}'); cookie name is now MoodleSession${desired}"
        else
            echo "[moodle] sessioncookie update attempted, but value remains '${after:-<unset>}' (desired '${desired}')"
        fi
    fi

    # Clean up the legacy/no-op 'cookieprefix' row if a previous deploy wrote one.
    php "${MOODLE_DIR}/admin/cli/cfg.php" --name=cookieprefix --set='' >/dev/null 2>&1 || true
}

# ── Inject agent config into config.php (once, before require_once) ───────────
# Only runs if the marker is missing. To re-inject (e.g. after changing env vars),
# remove the "CODERUNNER_AGENT_URL" line from config.php and restart the container.
inject_agent_config() {
    [ -f "${CONFIG_PHP}" ] || return 0

    # Skip if already injected
    if grep -q "CODERUNNER_AGENT_URL" "${CONFIG_PHP}"; then
        echo "[moodle] Agent config already present in config.php — skipping injection"
        return 0
    fi

    local tmpfile
    tmpfile=$(mktemp)
    cp "${CONFIG_PHP}" "${tmpfile}"

    # Find the require_once line number
    local req_line
    req_line=$(grep -n "require_once(__DIR__" "${tmpfile}" | head -1 | cut -d: -f1)
    if [ -z "${req_line}" ]; then
        rm -f "${tmpfile}"
        return 0
    fi

    # Rebuild config.php: everything before require_once → agent block → require_once onwards
    head -n "$((req_line - 1))" "${tmpfile}" > "${CONFIG_PHP}"

    if [ "${SSL_PROXY}" = "true" ]; then
        cat >> "${CONFIG_PHP}" << CFGEOF
// ── CodeRunner Agent production config ───────────────────────────────────────
\$CFG->sslproxy = true;
define('CODERUNNER_AGENT_URL', '${AGENT_URL}');

CFGEOF
    else
        cat >> "${CONFIG_PHP}" << CFGEOF
// ── CodeRunner Agent development config ──────────────────────────────────────
\$CFG->cachejs        = false;
\$CFG->jsrev          = -1;
\$CFG->cachetemplates = false;
define('CODERUNNER_AGENT_URL', '${AGENT_URL}');

CFGEOF
    fi

    tail -n +"${req_line}" "${tmpfile}" >> "${CONFIG_PHP}"
    chown www-data:www-data "${CONFIG_PHP}"
    rm -f "${tmpfile}"
    echo "[moodle] Agent config injected into config.php (sslproxy=${SSL_PROXY})"
}

# ── Wait for MySQL ────────────────────────────────────────────────────────────
echo "[moodle] Waiting for MySQL at ${MOODLE_DB_HOST}..."
until mysql -h "${MOODLE_DB_HOST}" -u"${MOODLE_DB_USER}" \
      -p"${MOODLE_DB_PASS}" "${MOODLE_DB_NAME}" \
      --ssl=0 -e "SELECT 1" \
      >/dev/null 2>&1; do
    sleep 3
done
echo "[moodle] MySQL is ready."

configure_php_timezone

# ── Fix permissions ───────────────────────────────────────────────────────────
chown -R www-data:www-data "${MOODLE_DATA}" 2>/dev/null || true

# ── First-time install ────────────────────────────────────────────────────────
if [ ! -f "${CONFIG_PHP}" ]; then
    echo "[moodle] Running Moodle installer (wwwroot=${WWWROOT})..."
    install_args=(
        --wwwroot="${WWWROOT}"
        --dataroot="${MOODLE_DATA}"
        --dbtype=mysqli
        --dbhost="${MOODLE_DB_HOST}"
        --dbname="${MOODLE_DB_NAME}"
        --dbuser="${MOODLE_DB_USER}"
        --dbpass="${MOODLE_DB_PASS}"
        --adminuser="${MOODLE_ADMIN_USER}"
        --adminpass="${MOODLE_ADMIN_PASS}"
        --adminemail="${MOODLE_ADMIN_EMAIL}"
        --fullname="CodeRunner Agent Course"
        --shortname="CRA"
        --non-interactive
        --agree-license
    )
    if php "${MOODLE_DIR}/admin/cli/install.php" --help 2>&1 | grep -q -- "--timezone"; then
        install_args+=(--timezone="${MOODLE_TIMEZONE_VALUE}")
    fi
    php "${MOODLE_DIR}/admin/cli/install.php" "${install_args[@]}"
    echo "[moodle] Installation complete."
fi

# ── Inject agent config (every boot, before require_once) ─────────────────────
inject_agent_config

# ── Upgrade DB (picks up newly mounted plugins) ───────────────────────────────
echo "[moodle] Running Moodle upgrade (plugin detection)..."
php "${MOODLE_DIR}/admin/cli/upgrade.php" --non-interactive 2>&1 | tail -5 || true

configure_moodle_timezone
configure_session_cookie

# ── Cron (every minute) + nightly cron-log truncation ───────────────────────
# cron.d uses a minimal PATH (/usr/bin:/bin); PHP from the image lives in /usr/local/bin,
# so a bare `php` often never runs and async work (e.g. course restore) stays "Process pending".
PHP_CLI="/usr/local/bin/php"
CRON_LOG="${MOODLE_DATA}/moodle-cron.log"
touch "${CRON_LOG}" 2>/dev/null || true
chown www-data:www-data "${CRON_LOG}" 2>/dev/null || true
cat > /etc/cron.d/moodle-cron <<CRONEOF
SHELL=/bin/sh
PATH=/usr/local/bin:/usr/bin:/bin
* * * * * www-data ${PHP_CLI} ${MOODLE_DIR}/admin/cli/cron.php --keep-alive=0 >>${CRON_LOG} 2>&1
0 3 * * * root /usr/bin/find ${MOODLE_DATA} -maxdepth 1 -name 'moodle-cron.log' -size +50M -exec /usr/bin/truncate -s 0 {} \;

CRONEOF
chmod 0644 /etc/cron.d/moodle-cron
rm -f /etc/cron.d/moodle-cron.off 2>/dev/null || true
pkill cron 2>/dev/null || true
cron

# ── Configure Apache sub-path alias (if wwwroot has a path) ───────────────────
MOODLE_PATH=$(echo "${WWWROOT}" | sed -n 's|https\?://[^/]*\(/.*\)|\1|p')
if [ -n "${MOODLE_PATH}" ]; then
    cat > /etc/apache2/conf-enabled/moodle-subpath.conf << APACHEEOF
Alias ${MOODLE_PATH} /var/www/html/moodle
<Directory /var/www/html/moodle>
    AllowOverride All
    Require all granted
</Directory>
APACHEEOF
    echo "[moodle] Apache Alias configured: ${MOODLE_PATH} -> /var/www/html/moodle"
fi

echo "[moodle] Starting Apache..."
exec "$@"
