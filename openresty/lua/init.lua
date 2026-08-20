-- Runs once in the nginx master process before workers are forked.
-- Sets up the global `auto_ssl` instance (referenced by name from
-- conf.d/edge.conf and by init_worker_by_lua_block in nginx.conf).

local redis_client = require "redis_client"
local autossl_whitelist = require "autossl_whitelist"

auto_ssl = (require "resty.auto-ssl").new()

auto_ssl:set("dir", "/etc/resty-auto-ssl")
auto_ssl:set("storage_adapter", "resty.auto-ssl.storage_adapters.redis")

local redis_opts = redis_client.connection_options()
if redis_opts then
    auto_ssl:set("redis", {
        host = redis_opts.host,
        port = redis_opts.port,
        auth = redis_opts.password,
        db = redis_opts.db,
    })
end

auto_ssl:set("allow_domain", autossl_whitelist.allow_domain)

-- The ACME contact email is no longer read from a static env var here —
-- it's editable live from the panel's Settings page and kept in sync by
-- acme_contact.lua, called right before each issuance attempt (see
-- conf.d/edge.conf). ACME_EMAIL still exists as an env var, but only to
-- seed that setting's initial value on the panel's first boot.

auto_ssl:init()
