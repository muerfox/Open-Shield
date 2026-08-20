# Only fires for errors nginx/Lua generate themselves (origin unreachable
# -> 502/504, no live upstream -> 503, an uncaught Lua error -> 500) —
# NOT for a real origin's own 4xx/5xx responses, which pass straight
# through untouched (proxy_intercept_errors defaults to off).
error_page 500 502 503 504 = @edge_error;
location @edge_error {
    internal;
    content_by_lua_block {
        require("error_page").render(ngx.status)
    }
}
