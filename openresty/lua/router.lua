-- Resolves the incoming Host header to a domain's CDN config (origin,
-- cache, rate-limit settings) as synced into Redis by the panel.
-- Results are cached in a shared dict for a couple seconds to avoid
-- hitting Redis on every single request.
--
-- Supports one level of wildcard domain (e.g. "*.example.com", matching
-- "anything.example.com" but not "a.b.example.com" or the bare apex,
-- same semantics as DNS/TLS wildcards generally): if there's no exact
-- match for the requested host, falls back to looking up "*." plus
-- everything after the first label.

local cjson = require "cjson.safe"
local redis_client = require "redis_client"

local _M = {}

local CACHE_TTL = 2
local waf_cache = ngx.shared.waf_cache

local function bool(v)
    return v == "1"
end

-- Looks up a single Redis key (either an exact host or a "*.parent"
-- wildcard pattern) and returns a decoded cfg table, or nil.
local function resolve_key(key)
    local cache_key = "domain:" .. key
    local cached = waf_cache:get(cache_key)
    if cached == "__MISS__" then
        return nil
    elseif cached then
        return cjson.decode(cached)
    end

    local red, err = redis_client.get_connection()
    if not red then
        ngx.log(ngx.ERR, "router: no redis connection: ", err)
        return nil
    end

    local res, err = red:hgetall("domain:" .. key)
    if not res then
        ngx.log(ngx.ERR, "router: hgetall failed: ", err)
        redis_client.release(red)
        return nil
    end

    if #res == 0 then
        redis_client.release(red)
        waf_cache:set(cache_key, "__MISS__", CACHE_TTL)
        return nil
    end

    local h = red:array_to_hash(res)
    redis_client.release(red)

    local cfg = {
        origin_scheme = h.origin_scheme or "http",
        origin_host = h.origin_host,
        origin_port = tonumber(h.origin_port) or 80,
        proxied = bool(h.proxied),
        waf_enabled = bool(h.waf_enabled),
        ssl_mode = h.ssl_mode or "off",
        cache_enabled = bool(h.cache_enabled),
        cache_ttl = tonumber(h.cache_ttl) or 60,
        rate_limit_enabled = bool(h.rate_limit_enabled),
        rate_limit_requests = tonumber(h.rate_limit_requests) or 100,
        rate_limit_window = tonumber(h.rate_limit_window) or 10,
    }

    waf_cache:set(cache_key, cjson.encode(cfg), CACHE_TTL)
    return cfg
end

-- cfg.host is always the actual requested hostname (used for cache keys,
-- rate-limit buckets, and log/event display — each subdomain gets its own).
-- cfg.domain_key is the Redis identity of the *matched configuration*
-- (the wildcard pattern itself when matched via wildcard) — used to scope
-- WAF rules/IP blocklists/manual SSL certs, since that's what the admin
-- actually configured in the panel.
function _M.resolve(host)
    local cfg = resolve_key(host)
    if cfg then
        cfg.host = host
        cfg.domain_key = host
        return cfg
    end

    local parent = host:match("^[^.]+%.(.+)$")
    if not parent then
        return nil
    end

    local wildcard_key = "*." .. parent
    cfg = resolve_key(wildcard_key)
    if not cfg then
        return nil
    end

    cfg.host = host
    cfg.domain_key = wildcard_key
    return cfg
end

-- Wires up the $upstream_* / $no_cache nginx variables used by the
-- proxy_pass / proxy_cache directives in conf.d/edge.conf.
function _M.configure_upstream(cfg)
    ngx.var.upstream_scheme = cfg.origin_scheme
    ngx.var.upstream_host = cfg.origin_host
    ngx.var.upstream_port = tostring(cfg.origin_port)
    ngx.var.no_cache = cfg.cache_enabled and "0" or "1"
    ngx.ctx.domain_cfg = cfg
end

return _M
