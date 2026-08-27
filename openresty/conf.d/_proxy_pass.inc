# Shared proxy_pass/cache config, included from both the :80 (ssl_mode "off")
# and :443 locations after edge.lua's access_by_lua_block has resolved the
# domain and set $upstream_* / $no_cache.

header_filter_by_lua_block {
    -- Assigning ngx.header replaces the header outright (unlike add_header,
    -- which would leave nginx's own "Server: openresty/..." in place
    -- alongside a second one).
    ngx.header["Server"] = "OpenShield"

    local cfg = ngx.ctx.domain_cfg
    if cfg and cfg.cache_enabled then
        ngx.header["X-Accel-Expires"] = tostring(cfg.cache_ttl)
    end
}

proxy_http_version 1.1;
# Fires error_page (_error_page.inc) for a real 5xx *response* from the
# origin too, not just a connection-level failure to reach it — see that
# file for exactly which codes and why nothing else is affected.
proxy_intercept_errors on;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Connection "";

proxy_cache edge_cache;
proxy_cache_key $scheme$host$request_uri;
proxy_cache_valid 200 302 60s;
proxy_cache_bypass $no_cache;
proxy_no_cache $no_cache;
add_header X-Cache-Status $upstream_cache_status always;

proxy_pass $upstream_scheme://$upstream_host:$upstream_port;
