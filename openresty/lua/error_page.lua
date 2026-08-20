-- Renders a branded HTML error page and finalizes the response. Used for
-- errors the edge itself generates (WAF blocks, unknown domain, origin
-- unreachable) — never for a real origin's own 4xx/5xx, which pass
-- through untouched (see conf.d/_error_page.inc: proxy_intercept_errors
-- defaults to off, so this only fires for nginx/Lua-level errors).
--
-- Deliberately generic per status code — never includes *why* a WAF block
-- happened (matched rule/pattern) on the public page, since that would
-- hand an attacker a debugging oracle. The real reason is still recorded
-- in the panel's Logs page via waf.lua's log_event.

local _M = {}

local INFO = {
    [400] = { title = "Bad Request", message = "The request could not be understood." },
    [403] = { title = "Blocked", message = "This request was blocked by the Open-Shield WAF." },
    [404] = { title = "Domain Not Found", message = "This domain isn't configured on this server." },
    [429] = { title = "Too Many Requests", message = "You're sending requests too quickly. Please slow down and try again shortly." },
    [500] = { title = "Something Went Wrong", message = "An unexpected error occurred while processing your request." },
    [502] = { title = "Bad Gateway", message = "The origin server refused the connection or sent an invalid response." },
    [503] = { title = "Service Unavailable", message = "The origin server is temporarily unavailable. Please try again shortly." },
    [504] = { title = "Gateway Timeout", message = "The origin server took too long to respond." },
}

local function esc(s)
    if s == nil then
        return ""
    end
    local str = tostring(s)
    str = str:gsub("&", "&amp;")
    str = str:gsub("<", "&lt;")
    str = str:gsub(">", "&gt;")
    str = str:gsub('"', "&quot;")
    return str
end

function _M.render(status, custom_message)
    local info = INFO[status] or { title = "Error", message = "Something went wrong." }
    local message = custom_message or info.message
    local request_id = ngx.var.request_id or "-"

    ngx.status = status
    ngx.header["Content-Type"] = "text/html; charset=utf-8"
    ngx.header["Cache-Control"] = "no-store"

    ngx.say([[<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>]] .. status .. " &middot; " .. esc(info.title) .. [[</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: radial-gradient(circle at 50% 0%, #1a2332 0%, #0b0f17 65%);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #e6e9ef;
    padding: 1.5rem;
  }
  .card {
    max-width: 460px; width: 100%;
    background: #131a26;
    border: 1px solid #253044;
    border-radius: 16px;
    padding: 2.5rem 2rem;
    text-align: center;
    box-shadow: 0 20px 60px rgba(0,0,0,0.5);
    animation: rise 0.35s ease-out;
  }
  @keyframes rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  .icon {
    font-size: 2.75rem; line-height: 1;
    filter: drop-shadow(0 0 22px rgba(88,166,255,0.45));
    margin-bottom: 0.75rem;
  }
  .status-pill {
    font-weight: 800; font-size: 3rem; letter-spacing: -0.02em;
    background: linear-gradient(135deg, #58a6ff, #7ee3c9);
    -webkit-background-clip: text; background-clip: text; color: transparent;
    margin: 0 0 0.35rem;
  }
  h1 { font-size: 1.35rem; margin: 0 0 0.75rem; color: #f2f5fa; font-weight: 650; }
  p.message { color: #a9b4c4; line-height: 1.55; margin: 0; }
  .footer { margin-top: 1.75rem; padding-top: 1.25rem; border-top: 1px solid #253044; }
  .footer small { color: #5b667a; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.75rem; }
  .brand { color: #7c8aa5; font-size: 0.85rem; margin-top: 0.4rem; }
  .brand b { color: #9fb3d1; }
</style>
</head>
<body>
  <div class="card">
    <div class="icon">&#128737;&#65039;</div>
    <div class="status-pill">]] .. status .. [[</div>
    <h1>]] .. esc(info.title) .. [[</h1>
    <p class="message">]] .. esc(message) .. [[</p>
    <div class="footer">
      <small>Request ID: ]] .. esc(request_id) .. [[</small>
      <div class="brand">Protected by <b>Open&#8209;Shield</b></div>
    </div>
  </div>
</body>
</html>]])

    return ngx.exit(status)
end

return _M
