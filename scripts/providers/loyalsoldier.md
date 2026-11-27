# Loyalsoldier

`loyalsoldier-geoip` — the GeoIP lists of
[Loyalsoldier/geoip](https://github.com/Loyalsoldier/geoip), one file per country or service (`ru`,
`google`, `telegram`, `private`, …). Its `geoip.dat` is byte for byte the one
[Loyalsoldier/v2ray-rules-dat](https://github.com/Loyalsoldier/v2ray-rules-dat) ships.

- Format: plain CIDR, one per line, IPv4 and IPv6 mixed. Upstream writes these files itself; nothing is converted or hosted here. FIRC reads each line as a `subnet` or `subnet6` rule.
- Updated by upstream weekly; a router picks a change up on its list's interval.
- Large lists: `us` holds about 260 000 prefixes. FIRC's own measurements (`docs/limits.md`) put a subnet rule near 200 bytes of daemon memory, so check a list in the dialog's preview first on a router with 256 MB or less.
- License: CC-BY-SA-4.0. The data includes GeoLite2 data created by MaxMind, available from [maxmind.com](https://www.maxmind.com). The catalog only links to it.
