-- Keeps /etc/resty-auto-ssl/letsencrypt/conf.d/contact.sh (dehydrated's
-- ACME contact-email config) in sync with the panel's Settings page
-- (settings:acme_email in Redis), so it's editable live from the panel —
-- no rebuild/restart needed. Checked (at most once every 60s, via the
-- shared dict) right before an actual issuance attempt.

local redis_client = require "redis_client"

local _M = {}

local CONTACT_FILE = "/etc/resty-auto-ssl/letsencrypt/conf.d/contact.sh"
local CHECK_INTERVAL = 60
local cache = ngx.shared.auto_ssl_settings

function _M.sync()
    if cache:get("acme_email_checked") then
        return
    end
    cache:set("acme_email_checked", true, CHECK_INTERVAL)

    local red, err = redis_client.get_connection()
    if not red then
        ngx.log(ngx.WARN, "acme_contact: no redis connection: ", err)
        return
    end
    local email = red:get("settings:acme_email")
    redis_client.release(red)

    if not email or email == ngx.null or email == "" then
        return
    end

    -- The panel already validates this, but defend in depth: this value
    -- is written into a shell config file dehydrated sources, so refuse
    -- anything that could break out of the double-quoted string context.
    if email:find('["\'$`\\\n]') then
        ngx.log(ngx.ERR, "acme_contact: refusing to write unsafe contact email value")
        return
    end

    if cache:get("acme_email_value") == email then
        return
    end

    os.execute("mkdir -p /etc/resty-auto-ssl/letsencrypt/conf.d")
    local f = io.open(CONTACT_FILE, "w")
    if not f then
        ngx.log(ngx.ERR, "acme_contact: failed to open ", CONTACT_FILE, " for writing")
        return
    end
    f:write('CONTACT_EMAIL="' .. email .. '"\n')
    f:close()
    cache:set("acme_email_value", email)
    ngx.log(ngx.NOTICE, "acme_contact: updated Let's Encrypt contact email")
end

return _M
