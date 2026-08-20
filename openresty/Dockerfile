FROM openresty/openresty:1.31.1.1-alpine-fat

RUN apk add --no-cache bash curl diffutils findutils grep sed coreutils openssl build-base perl

# --- lua-resty-auto-ssl (Let's Encrypt) + its runtime deps, built entirely
# from vendored source under vendor/ — no PyPI/luarocks.org/GitHub network
# access needed at image-build time. See vendor/VERSIONS.md for exact pins.
COPY vendor/ /usr/src/vendor/

# sockproc (small C helper auto-ssl shells out through) from vendored source.
RUN cd /usr/src/vendor/sockproc && make

# lua-resty-http and shell-games are auto-ssl's declared rock dependencies;
# `luarocks make <rockspec>` builds/installs whatever's in the current
# directory and never fetches anything itself, so this stays fully offline
# as long as the source is already present (which it is, via COPY above).
RUN cd /usr/src/vendor/lua-resty-http \
    && luarocks make lua-resty-http-0.18.0-0.rockspec --deps-mode=none \
    && cd /usr/src/vendor/shell-games \
    && luarocks make shell-games-1.1.0-1.rockspec --deps-mode=none

# auto-ssl's own Makefile normally curls down `dehydrated`, lua-resty-shell's
# shell.lua, and the sockproc source at build time (see its Makefile) — we
# instead drop the already-vendored copies straight into the exact paths
# and "stamp" files it expects, so `make`'s dependency tracking sees those
# steps as already done and skips the network fetches entirely.
RUN mkdir -p /usr/src/vendor/lua-resty-auto-ssl/build/bin \
    && cp /usr/src/vendor/dehydrated /usr/src/vendor/lua-resty-auto-ssl/build/bin/dehydrated \
    && chmod +x /usr/src/vendor/lua-resty-auto-ssl/build/bin/dehydrated \
    && cp /usr/src/vendor/sockproc/sockproc /usr/src/vendor/lua-resty-auto-ssl/build/bin/sockproc \
    && chmod +x /usr/src/vendor/lua-resty-auto-ssl/build/bin/sockproc \
    && cp /usr/src/vendor/lua-resty-shell/shell.lua /usr/src/vendor/lua-resty-auto-ssl/lib/resty/auto-ssl/vendor/shell.lua \
    && touch /usr/src/vendor/lua-resty-auto-ssl/build/stamp-dehydrated-2-05eda91a2fbaed1e13c733230238fc68475c535e \
    && touch /usr/src/vendor/lua-resty-auto-ssl/build/stamp-lua-resty-shell-955243d70506c21e7cc29f61d745d1a8a718994f \
    && touch /usr/src/vendor/lua-resty-auto-ssl/build/stamp-sockproc-2-92aba736027bb5d96e190b71555857ac5bb6b2be \
    && cd /usr/src/vendor/lua-resty-auto-ssl \
    && luarocks make lua-resty-auto-ssl-0.13.1-1.rockspec --deps-mode=none

RUN rm -rf /usr/src/vendor \
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
