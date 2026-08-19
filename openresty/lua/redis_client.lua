-- Shared Redis connection helper. Parses REDIS_URL once
-- (redis://[:password@]host:port[/db]) and hands out pooled connections.

local redis = require "resty.redis"

local _M = {}

local parsed

local function parse_url()
    local url = os.getenv("REDIS_URL")
    if not url then
        return nil, "REDIS_URL not set"
    end

    local password, host, port, db =
        url:match("^redis://:?([^@]-)@?([%w%.%-_]+):(%d+)/?(%d*)$")

    if not host then
        return nil, "could not parse REDIS_URL"
    end

    return {
        password = (password ~= "" and password) or nil,
        host = host,
        port = tonumber(port),
        db = tonumber(db) or 0,
    }
end

function _M.get_connection()
    if not parsed then
        local err
        parsed, err = parse_url()
        if not parsed then
            ngx.log(ngx.ERR, "redis_client: ", err)
            return nil, err
        end
    end

    local red = redis:new()
    red:set_timeout(1000)

    local ok, err = red:connect(parsed.host, parsed.port)
    if not ok then
        ngx.log(ngx.ERR, "redis_client: connect failed: ", err)
        return nil, err
    end

    if parsed.password then
        local ok, err = red:auth(parsed.password)
        if not ok then
            ngx.log(ngx.ERR, "redis_client: auth failed: ", err)
            return nil, err
        end
    end

    if parsed.db and parsed.db ~= 0 then
        red:select(parsed.db)
    end

    return red
end

function _M.release(red)
    if not red then
        return
    end
    local ok, err = red:set_keepalive(10000, 100)
    if not ok then
        ngx.log(ngx.WARN, "redis_client: set_keepalive failed: ", err)
    end
end

-- Exposed for lua-resty-auto-ssl's redis storage adapter config.
function _M.connection_options()
    if not parsed then
        parsed = parse_url()
    end
    return parsed
end

return _M
