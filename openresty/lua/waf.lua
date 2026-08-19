-- Inspects each request against IP blocklists, header/URL/body pattern
-- rules and a simple per-domain rate limit, all synced into Redis by the
-- panel. Call _M.enforce(cfg) from access_by_lua; it ngx.exit()s directly
-- on a block/rate-limit and otherwise returns normally.

local cjson = require "cjson.safe"
local redis_client = require "redis_client"

local _M = {}

local RULES_CACHE_TTL = 2
local waf_cache = ngx.shared.waf_cache

local function get_client_ip()
    return ngx.var.remote_addr
end

local function log_event(red, cfg, ip, action, reason)
    local event = cjson.encode({
        ts = ngx.now(),
        domain = cfg.host,
        ip = ip,
        action = action,
        reason = reason,
        uri = ngx.var.request_uri,
    })
    local ok, err = red:lpush("waf:log", event)
    if ok then
        red:ltrim("waf:log", 0, 499)
    else
        ngx.log(ngx.WARN, "waf: failed to push event: ", err)
    end
end

local function deny(red, cfg, ip, status, reason)
    log_event(red, cfg, ip, "block", reason)
    redis_client.release(red)
    ngx.status = status
    ngx.header["Content-Type"] = "text/plain"
    ngx.say("Blocked by Open-Shield WAF")
    ngx.exit(status)
end

-- ---- IPv4 CIDR matching -------------------------------------------------

local function ip4_to_int(ip)
    local a, b, c, d = ip:match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")
    if not a then
        return nil
    end
    a, b, c, d = tonumber(a), tonumber(b), tonumber(c), tonumber(d)
    if a > 255 or b > 255 or c > 255 or d > 255 then
        return nil
    end
    return (a * 16777216) + (b * 65536) + (c * 256) + d
end

local function ip_in_cidr(ip, cidr)
    local net, bits = cidr:match("^([%d%.]+)/(%d+)$")
    if not net then
        return false
    end
    bits = tonumber(bits)
    local ip_int = ip4_to_int(ip)
    local net_int = ip4_to_int(net)
    if not ip_int or not net_int or bits > 32 then
        return false
    end
    if bits == 0 then
        return true
    end
    local mask = bit.lshift(0xFFFFFFFF, 32 - bits)
    -- normalize to unsigned 32-bit range for comparison
    mask = bit.band(mask, 0xFFFFFFFF)
    return bit.band(ip_int, mask) == bit.band(net_int, mask)
end

-- ---- Data loading (with short-lived shared-dict caching) ---------------

local function fetch_cached_json(red, redis_key, cache_key, default_value)
    local cached = waf_cache:get(cache_key)
    if cached then
        return cjson.decode(cached)
    end
    local res, err = red:get(redis_key)
    if not res or res == ngx.null then
        res = default_value
    end
    waf_cache:set(cache_key, res, RULES_CACHE_TTL)
    return cjson.decode(res)
end

local function load_rules(red)
    return fetch_cached_json(red, "waf:rules", "waf:rules:cache", "[]")
end

local function load_cidrs(red, host)
    local global = fetch_cached_json(red, "waf:blocked_cidrs:global", "waf:cidrs:global", "[]")
    local scoped = fetch_cached_json(red, "waf:blocked_cidrs:" .. host, "waf:cidrs:" .. host, "[]")
    return global, scoped
end

-- ---- Rule evaluation -----------------------------------------------------

local function get_haystack(rule, body)
    if rule.target == "url" then
        return ngx.var.request_uri
    elseif rule.target == "header" then
        if not rule.header_name then
            return nil
        end
        local headers = ngx.req.get_headers()
        return headers[rule.header_name]
    elseif rule.target == "body" then
        return body
    end
    return nil
end

local function rule_matches(rule, haystack)
    if not haystack then
        return false
    end
    if rule.match_type == "exact" then
        return haystack == rule.value
    elseif rule.match_type == "regex" then
        local m = ngx.re.find(haystack, rule.value, "jo")
        return m ~= nil
    else -- "contains"
        return string.find(haystack, rule.value, 1, true) ~= nil
    end
end

-- ---- Public API ------------------------------------------------------

function _M.enforce(cfg)
    local ip = get_client_ip()
    local red, err = redis_client.get_connection()
    if not red then
        ngx.log(ngx.ERR, "waf: no redis connection, failing open: ", err)
        return
    end

    -- 1. Exact-match IP blocklist (global + per-domain).
    local blocked, err = red:sismember("waf:blocked_ips:global", ip)
    if not blocked or blocked == 0 then
        blocked = red:sismember("waf:blocked_ips:" .. cfg.host, ip)
    end
    if blocked and blocked == 1 then
        return deny(red, cfg, ip, 403, "ip_blocklist")
    end

    -- 2. CIDR blocklist (global + per-domain).
    local global_cidrs, scoped_cidrs = load_cidrs(red, cfg.host)
    for _, cidr in ipairs(global_cidrs) do
        if ip_in_cidr(ip, cidr) then
            return deny(red, cfg, ip, 403, "cidr_blocklist:" .. cidr)
        end
    end
    for _, cidr in ipairs(scoped_cidrs) do
        if ip_in_cidr(ip, cidr) then
            return deny(red, cfg, ip, 403, "cidr_blocklist:" .. cidr)
        end
    end

    -- 3. Rate limiting.
    if cfg.rate_limit_enabled then
        local key = "rl:" .. cfg.host .. ":" .. ip
        local count, err = red:incr(key)
        if count then
            if count == 1 then
                red:expire(key, cfg.rate_limit_window)
            end
            if count > cfg.rate_limit_requests then
                return deny(red, cfg, ip, 429, "rate_limit")
            end
        end
    end

    -- 4. Pattern rules (url / header / body), global + per-domain.
    local rules = load_rules(red)
    local applicable = {}
    local needs_body = false
    for _, rule in ipairs(rules) do
        if rule.domain == nil or rule.domain == cjson.null or rule.domain == cfg.host then
            table.insert(applicable, rule)
            if rule.target == "body" then
                needs_body = true
            end
        end
    end

    local body = nil
    if needs_body then
        ngx.req.read_body()
        body = ngx.req.get_body_data()
    end

    for _, rule in ipairs(applicable) do
        local haystack = get_haystack(rule, body)
        if rule_matches(rule, haystack) then
            local reason = rule.name .. " (" .. rule.target .. " " .. rule.match_type .. ")"
            if rule.action == "block" then
                return deny(red, cfg, ip, 403, reason)
            else
                log_event(red, cfg, ip, "log", reason)
            end
        end
    end

    redis_client.release(red)
end

return _M
