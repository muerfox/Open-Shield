-- allow_domain callback for lua-resty-auto-ssl: only issue/renew
-- certificates for domains the panel has actually configured (present in
-- the `domains:index` Redis set), to avoid ACME issuance being triggered
-- by arbitrary/bogus SNI hostnames.

local redis_client = require "redis_client"

local _M = {}

function _M.allow_domain(domain, auto_ssl, ssl_options, renewal)
    if not domain then
        return false
    end
    domain = domain:lower()

    local red, err = redis_client.get_connection()
    if not red then
        ngx.log(ngx.ERR, "autossl_whitelist: no redis connection: ", err)
        return false
    end

    local ok, err = red:sismember("domains:index", domain)
    redis_client.release(red)

    if err then
        ngx.log(ngx.ERR, "autossl_whitelist: sismember failed: ", err)
        return false
    end

    return ok == 1
end

return _M
