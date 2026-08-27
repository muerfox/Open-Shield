-- Generates a small nginx config file (one pair of server blocks per
-- domain that has customized proxy_connect_timeout / proxy_send_timeout /
-- proxy_read_timeout / max body size — see domains/form.html) and
-- triggers a graceful `nginx -s reload` when it changes.
--
-- Unlike everything else in Open-Shield, this genuinely can't be made to
-- take effect instantly: none of those directives accept nginx variables
-- (confirmed against nginx's own docs), so there's no way to drive them
-- from Lua/Redis per-request the way routing/WAF/etc. are. A reload is
-- the only mechanism nginx offers — but it's the same zero-downtime
-- graceful reload `nginx -s reload` always does (new workers spun up with
-- the new config, old ones drained; nginx validates the config first and
-- keeps running the old one if it's broken), just triggered automatically
-- by this timer instead of a human running it.
--
-- Domains using the defaults for all four settings don't get a dedicated
-- block at all — they keep falling through to the shared catch-all
-- server blocks in conf.d/edge.conf, which is the common case and keeps
-- the generated file small.

local redis_client = require "redis_client"

local _M = {}

local GENERATED_FILE = "/etc/openresty/conf.d/generated/domain_limits.conf"
local REGEN_INTERVAL = 20
local state = ngx.shared.waf_cache

local DEFAULT_CONNECT = 60
local DEFAULT_SEND = 60
local DEFAULT_READ = 60
local DEFAULT_BODY_MB = 20

local TEMPLATE_80 = [[
server {
    listen 80;
    server_name %s;
    client_max_body_size %s;
    proxy_connect_timeout %ds;
    proxy_send_timeout %ds;
    proxy_read_timeout %ds;

    set $upstream_scheme '';
    set $upstream_host '';
    set $upstream_port '';
    set $no_cache '1';

    include /etc/openresty/conf.d/_error_page.inc;

    location /.well-known/acme-challenge/ {
        content_by_lua_block {
            auto_ssl:challenge_server()
        }
    }

    location / {
        access_by_lua_block {
            require("edge").handle(false)
        }
        include /etc/openresty/conf.d/_proxy_pass.inc;
    }
}
]]

local TEMPLATE_443 = [[
server {
    listen 443 ssl;
    server_name %s;
    client_max_body_size %s;
    proxy_connect_timeout %ds;
    proxy_send_timeout %ds;
    proxy_read_timeout %ds;

    ssl_certificate_by_lua_block {
        require("edge_ssl").certificate()
    }
    ssl_certificate     /etc/ssl/resty-auto-ssl-fallback.crt;
    ssl_certificate_key /etc/ssl/resty-auto-ssl-fallback.key;

    set $upstream_scheme '';
    set $upstream_host '';
    set $upstream_port '';
    set $no_cache '1';

    include /etc/openresty/conf.d/_error_page.inc;

    location / {
        access_by_lua_block {
            require("edge").handle(true)
        }
        include /etc/openresty/conf.d/_proxy_pass.inc;
    }
}
]]

-- Panel-side validation already restricts these to sane characters/ranges;
-- this is defense in depth before writing directly into a config file.
local function is_safe_server_name(name)
    return type(name) == "string" and #name > 0 and #name < 256 and name:find("^[%*%.%w%-]+$") ~= nil
end

local function is_safe_number(n, max)
    return type(n) == "number" and n == n and n >= 0 and n <= max  -- n == n rules out NaN
end

local function body_size_directive(mb)
    if mb == 0 then
        return "0"
    end
    return mb .. "m"
end

local function needs_own_block(connect, send, read, body_mb)
    return connect ~= DEFAULT_CONNECT or send ~= DEFAULT_SEND or read ~= DEFAULT_READ or body_mb ~= DEFAULT_BODY_MB
end

local function build_config(red)
    local names, err = red:smembers("domains:index")
    if not names then
        ngx.log(ngx.ERR, "domain_limits: failed to list domains:index: ", err)
        return nil
    end

    local parts = {}
    for _, name in ipairs(names) do
        local res, hget_err = red:hgetall("domain:" .. name)
        if not res then
            ngx.log(ngx.ERR, "domain_limits: hgetall failed for ", name, ": ", hget_err)
        elseif #res > 0 then
            local h = red:array_to_hash(res)
            if h.proxied == "1" and is_safe_server_name(name) then
                local connect = tonumber(h.proxy_connect_timeout) or DEFAULT_CONNECT
                local send = tonumber(h.proxy_send_timeout) or DEFAULT_SEND
                local read = tonumber(h.proxy_read_timeout) or DEFAULT_READ
                local body_mb = tonumber(h.max_body_size_mb)
                if body_mb == nil then
                    body_mb = DEFAULT_BODY_MB
                end

                if is_safe_number(connect, 3600) and is_safe_number(send, 3600)
                    and is_safe_number(read, 3600) and is_safe_number(body_mb, 10240)
                    and needs_own_block(connect, send, read, body_mb)
                then
                    local body_directive = body_size_directive(body_mb)
                    table.insert(parts, string.format(TEMPLATE_80, name, body_directive, connect, send, read))
                    table.insert(parts, string.format(TEMPLATE_443, name, body_directive, connect, send, read))
                end
            end
        end
    end

    return table.concat(parts, "\n")
end

local function write_and_reload(content)
    local f, err = io.open(GENERATED_FILE, "w")
    if not f then
        ngx.log(ngx.ERR, "domain_limits: failed to open ", GENERATED_FILE, " for writing: ", err)
        return
    end
    f:write(content)
    f:close()

    ngx.log(ngx.NOTICE, "domain_limits: config changed, reloading nginx")
    local ok, err2, err3 = os.execute("/usr/local/openresty/bin/openresty -t -q && /usr/local/openresty/bin/openresty -s reload")
    if not ok then
        ngx.log(ngx.ERR, "domain_limits: nginx reload failed: ", tostring(err2), " ", tostring(err3))
    end
end

local function do_regenerate()
    local red, err = redis_client.get_connection()
    if not red then
        ngx.log(ngx.WARN, "domain_limits: no redis connection: ", err)
        return
    end

    local content = build_config(red)
    redis_client.release(red)

    if content == nil then
        return
    end

    local cache_key = "domain_limits_content"
    if state:get(cache_key) == content then
        return
    end

    write_and_reload(content)
    local ok, set_err = state:set(cache_key, content)
    if not ok then
        ngx.log(ngx.ERR, "domain_limits: failed to cache generated content: ", set_err)
    end
end

local function tick(premature)
    if premature then
        return
    end

    -- Only one worker performs this per interval (same technique
    -- lua-resty-auto-ssl's own renewal job uses, via ngx.shared:add()'s
    -- "fails if key already exists" semantics).
    local got_lock = state:add("domain_limits_lock", true, REGEN_INTERVAL - 0.001)
    if got_lock then
        local ok, run_err = pcall(do_regenerate)
        if not ok then
            ngx.log(ngx.ERR, "domain_limits: regenerate failed: ", run_err)
        end
    end

    local timer_ok, timer_err = ngx.timer.at(REGEN_INTERVAL, tick)
    if not timer_ok and timer_err ~= "process exiting" then
        ngx.log(ngx.ERR, "domain_limits: failed to reschedule timer: ", timer_err)
    end
end

function _M.spawn()
    local ok, err = ngx.timer.at(0, tick)
    if not ok then
        ngx.log(ngx.ERR, "domain_limits: failed to start timer: ", err)
    end
end

return _M
