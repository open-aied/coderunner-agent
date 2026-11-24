FROM php:8.3-apache-bookworm

# ── System packages + PHP extensions required by Moodle ──────────────────────
RUN apt-get update && apt-get install -y \
    libfreetype6-dev libjpeg62-turbo-dev libpng-dev \
    libzip-dev libicu-dev libxml2-dev libxslt-dev \
    libonig-dev zlib1g-dev libldap2-dev \
    git unzip curl default-mysql-client cron \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install -j"$(nproc)" \
        gd mysqli pdo pdo_mysql \
        zip intl xml xsl soap \
        mbstring opcache exif \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── PHP settings for Moodle ───────────────────────────────────────────────────
RUN { \
    echo "max_input_vars = 5000"; \
    echo "post_max_size = 64M"; \
    echo "upload_max_filesize = 64M"; \
    echo "memory_limit = 256M"; \
    echo "date.timezone = Asia/Tokyo"; \
} > /usr/local/etc/php/conf.d/moodle.ini

# ── Apache: enable mod_rewrite, point DocumentRoot at moodle subdir ───────────
RUN a2enmod rewrite
RUN sed -i 's|/var/www/html|/var/www/html/moodle|g' \
        /etc/apache2/sites-enabled/000-default.conf \
    && sed -i 's|/var/www/html|/var/www/html/moodle|g' \
        /etc/apache2/apache2.conf || true
# Allow .htaccess overrides
RUN sed -i 's/AllowOverride None/AllowOverride All/g' /etc/apache2/apache2.conf || true

# ── Moodle data directory ─────────────────────────────────────────────────────
RUN mkdir -p /var/www/moodledata && chown www-data:www-data /var/www/moodledata

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /var/www/html
EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]
CMD ["apache2-foreground"]
