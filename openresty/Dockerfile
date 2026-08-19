FROM openresty/openresty:1.31.1.1-alpine-fat

RUN apk add --no-cache bash curl diffutils findutils grep sed coreutils openssl build-base perl

# lua-resty-auto-ssl (Let's Encrypt) + its runtime dependencies.
RUN luarocks install lua-resty-auto-ssl \
    && mkdir -p /etc/resty-auto-ssl \
    && chmod 777 /etc/resty-auto-ssl

# Static fallback cert so nginx has *something* to boot with; auto-ssl
# takes over per-SNI-host at runtime for any domain the panel knows about.
RUN openssl req -new -newkey rsa:2048 -days 3650 -nodes -x509 \
    -subj '/CN=sni-support-required-for-valid-ssl' \
    -keyout /etc/ssl/resty-auto-ssl-fallback.key \
    -out /etc/ssl/resty-auto-ssl-fallback.crt

RUN mkdir -p /var/cache/openresty/edge /etc/openresty/conf.d /etc/openresty/lua

COPY nginx.conf /usr/local/openresty/nginx/conf/nginx.conf
COPY conf.d/ /etc/openresty/conf.d/
COPY lua/ /etc/openresty/lua/

EXPOSE 80 443

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD curl -sf http://localhost:80/ >/dev/null || exit 1

CMD ["/usr/local/openresty/bin/openresty", "-g", "daemon off;"]
