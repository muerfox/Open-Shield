# Vendored source

Everything under this directory is vendored so `docker build` for the
`openresty` image needs no network access beyond pulling the base image and
Alpine's own `apk` packages. It's what `luarocks install lua-resty-auto-ssl`
would otherwise fetch at build time from GitHub/luarocks.org.

| Path | Source | Pinned to |
|---|---|---|
| `lua-resty-auto-ssl/` | https://github.com/auto-ssl/lua-resty-auto-ssl | tag `v0.13.1` |
| `lua-resty-http/` | https://github.com/ledgetech/lua-resty-http | tag `v0.18.0` (auto-ssl rock dependency) |
| `shell-games/` | https://github.com/GUI/lua-shell-games | tag `v1.1.0` (auto-ssl rock dependency) |
| `sockproc/` | https://github.com/juce/sockproc | commit `92aba736027bb5d96e190b71555857ac5bb6b2be` (pin from auto-ssl's `Makefile`) |
| `dehydrated` | https://github.com/lukas2511/dehydrated | commit `05eda91a2fbaed1e13c733230238fc68475c535e` (pin from auto-ssl's `Makefile`) |
| `lua-resty-shell/shell.lua` | https://github.com/juce/lua-resty-shell | commit `955243d70506c21e7cc29f61d745d1a8a718994f` (pin from auto-ssl's `Makefile`) |

`sockproc` and `dehydrated`/`shell.lua`'s exact pins come straight from
`lua-resty-auto-ssl`'s own `Makefile` (`DEHYDRATED_VERSION`,
`LUA_RESTY_SHELL_VERSION`, `SOCKPROC_VERSION`) — check that file when
bumping the `lua-resty-auto-ssl/` tag, since those pins can change between
releases.

## Refreshing

To bump `lua-resty-auto-ssl` to a newer release: re-clone
`lua-resty-auto-ssl/` at the new tag, re-check its `Makefile` for possibly
updated `dehydrated`/`lua-resty-shell`/`sockproc` pins, and re-fetch those
three accordingly. `lua-resty-http`/`shell-games` only need bumping if the
new rockspec's `dependencies` versions changed.
