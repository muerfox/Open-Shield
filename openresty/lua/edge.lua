-- Shared per-request entry point for both the :80 and :443 listeners.
-- Resolves the domain, decides whether to redirect HTTP -> HTTPS (only for
-- domains that actually want SSL), runs the WAF, and wires up the
-- proxy_pass/proxy_cache variables.

local router = require "router"
local waf = require "waf"

local _M = {}

function _M.handle(is_https)
    local cfg = router.resolve(ngx.var.host)
    if not cfg or not cfg.proxied then
        ngx.status = 404
        ngx.header["Content-Type"] = "text/plain"
        ngx.say("Unknown domain")
        return ngx.exit(404)
    end

    if not is_https and cfg.ssl_mode ~= "off" then
        ngx.header["Location"] = "https://" .. ngx.var.host .. ngx.var.request_uri
        return ngx.exit(ngx.HTTP_MOVED_PERMANENTLY)
    end

    router.configure_upstream(cfg)

    if cfg.waf_enabled then
        waf.enforce(cfg)
    end
end

return _M
