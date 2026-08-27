# Fires for 500/501/502/503/504 whether nginx/Lua generated them itself
# (origin unreachable, timeout, no live upstream, an uncaught Lua error)
# OR the origin returned them as a real response (e.g. the proxied app's
# own nginx/app server erroring out) — proxy_intercept_errors (in
# _proxy_pass.inc) makes that second case redirect here too, so the
# origin's own version banner/error page never reaches the visitor.
#
# Only these listed codes are affected: a real origin's 404, redirects,
# 401/403, etc. all still pass through completely untouched — nginx only
# redirects to error_page for status codes that actually have an
# error_page entry, proxy_intercept_errors just widens *when* that check
# happens (successful upstream responses, not just connection failures).
error_page 500 501 502 503 504 = @edge_error;
location @edge_error {
    internal;
    content_by_lua_block {
        require("error_page").render(ngx.status)
    }
}
