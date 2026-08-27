-- ssl_certificate_by_lua logic, factored out so both the shared
-- catch-all :443 server (conf.d/edge.conf) and the generated per-domain
-- :443 blocks (domain_limits.lua) can call the same code instead of
-- duplicating it.

local router = require "router"

local _M = {}

function _M.certificate()
    local ssl = require "ngx.ssl"
    local host = ssl.server_name()
    if not host then
        return
    end
    host = host:lower()

    local cfg = router.resolve(host)
    if cfg and cfg.ssl_mode == "manual" then
        -- Use domain_key (the *configured* domain — a wildcard pattern
        -- like "*.example.com" when matched via wildcard), not the raw
        -- SNI host, since that's the Redis key the panel actually stored
        -- the pasted cert/key under.
        require("manual_ssl").set_cert(cfg.domain_key)
    elseif cfg and cfg.ssl_mode == "auto" then
        -- lua-resty-auto-ssl has no built-in failure backoff: a domain
        -- that can't get a cert (bad DNS, port 80 unreachable, etc.)
        -- would otherwise retry a *synchronous* ACME request against
        -- Let's Encrypt on every single HTTPS request, blocking that
        -- request's whole handshake and risking Let's Encrypt's own rate
        -- limits. Skip the retry for a while after a failed attempt.
        local settings = ngx.shared.auto_ssl_settings
        local backoff_key = "issue_backoff:" .. host
        if not settings:get(backoff_key) then
            require("acme_contact").sync()
            auto_ssl:ssl_certificate()
            -- Same shared-dict key lua-resty-auto-ssl itself writes to
            -- on a successful issuance/cache hit.
            if not ngx.shared.auto_ssl:get("domain:fullchain_der:" .. host) then
                local ok, err = settings:set(backoff_key, true, 120)
                if not ok then
                    ngx.log(ngx.ERR, "auto-ssl backoff: failed to set flag for ", host, ": ", err)
                end
                ngx.log(ngx.WARN, "auto-ssl: cert issuance did not succeed for ", host, ", backing off retries for 120s")
            end
        end
    end
    -- ssl_mode "off" (or unknown host): fall through to the static
    -- fallback cert; edge.lua will still 404/serve normally.
end

return _M
