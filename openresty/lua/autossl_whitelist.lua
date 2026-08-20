-- allow_domain callback for lua-resty-auto-ssl: only issue/renew
-- certificates for domains the panel has configured with ssl_mode "auto",
-- to avoid ACME issuance being triggered by arbitrary/bogus SNI hostnames
-- or domains that are meant to use "off"/"manual" SSL instead.

local router = require "router"

local _M = {}

function _M.allow_domain(domain, auto_ssl, ssl_options, renewal)
    if not domain then
        return false
    end
    domain = domain:lower()

    local cfg = router.resolve(domain)
    return cfg ~= nil and cfg.proxied and cfg.ssl_mode == "auto"
end

return _M
