# RunetFreedom

The GeoSite and GeoIP of [runetfreedom/russia-v2ray-rules-dat](https://github.com/runetfreedom/russia-v2ray-rules-dat):
v2fly's domain-list-community and GeoIP plus Russian lists (`ru-blocked`, `ru-available-only-inside`,
`refilter`, `antifilter`, …). Upstream publishes one sing-box rule-set (SRS version 1) per tag on its
`release` branch; the catalog links to them and nothing is converted or hosted here.

- `runetfreedom-geosite` — about 2000 tags, `tag@attribute` variants included: domains (exact, suffix and regex rules).
- `runetfreedom-geoip` — about 270 tags: IPv4 and IPv6 prefixes.
- FIRC reads both formats as they are; every file of the release was checked with FIRC's parser.
- Too big for FIRC: `geosite-ru-blocked-all` and `geosite-antifilter-download` are about 12 MB each, over FIRC's 8 MiB list cap, so the catalog leaves them out. For the same data use `ru-blocked` (geosite and geoip), or the `refilter` and `antifilter` lists.
- Large lists that fit: `category-ads-all` (about 200 000 rules) and `geoip-us` are heavy for a router with 256 MB or less; check a list in the dialog's preview first.
- License: GPL-3.0. The catalog only links to it.
