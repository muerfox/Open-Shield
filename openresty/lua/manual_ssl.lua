-- Loads an admin-pasted PEM certificate/key (stored by the panel under
-- domain:<host>:ssl_cert / domain:<host>:ssl_key) and installs it for the
-- current TLS handshake. Parsed certs/keys are cached per-worker, keyed by
-- a content hash, so re-parsing only happens when the pasted cert changes.

local redis_client = require "redis_client"

local _M = {}

-- Worker-local cache: ngx.shared dicts can't hold cdata (parsed cert/key
-- objects), so this lives in a plain Lua table for the life of the worker.
local cache = {}

function _M.set_cert(host)
    local red, err = redis_client.get_connection()
    if not red then
        ngx.log(ngx.ERR, "manual_ssl: no redis connection: ", err)
        return false
    end

    local cert_pem, err1 = red:get("domain:" .. host .. ":ssl_cert")
    local key_pem, err2 = red:get("domain:" .. host .. ":ssl_key")
    redis_client.release(red)

    if not cert_pem or cert_pem == ngx.null or not key_pem or key_pem == ngx.null then
        ngx.log(ngx.WARN, "manual_ssl: no stored cert/key for ", host)
        return false
    end

    local hash = ngx.crc32_short(cert_pem .. key_pem)
    local entry = cache[host]

    if not entry or entry.hash ~= hash then
        local ssl = require "ngx.ssl"

        local cert_chain, cert_err = ssl.parse_pem_cert(cert_pem)
        if not cert_chain then
            ngx.log(ngx.ERR, "manual_ssl: failed to parse cert for ", host, ": ", cert_err)
            return false
        end

        local priv_key, key_err = ssl.parse_pem_priv_key(key_pem)
        if not priv_key then
            ngx.log(ngx.ERR, "manual_ssl: failed to parse key for ", host, ": ", key_err)
            return false
        end

        entry = { hash = hash, cert = cert_chain, key = priv_key }
        cache[host] = entry
    end

    local ssl = require "ngx.ssl"

    local ok, clear_err = ssl.clear_certs()
    if not ok then
        ngx.log(ngx.ERR, "manual_ssl: clear_certs failed: ", clear_err)
        return false
    end

    ok, err = ssl.set_cert(entry.cert)
    if not ok then
        ngx.log(ngx.ERR, "manual_ssl: set_cert failed: ", err)
        return false
    end

    ok, err = ssl.set_priv_key(entry.key)
    if not ok then
        ngx.log(ngx.ERR, "manual_ssl: set_priv_key failed: ", err)
        return false
    end

    return true
end

return _M
