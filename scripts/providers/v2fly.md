# V2Fly

`v2fly-geoip` — the GeoIP lists of [v2fly/geoip](https://github.com/v2fly/geoip), one file per country
plus `private`, `test` and `zz`.

- Format: plain CIDR, one per line, IPv4 and IPv6 mixed, written by upstream; nothing is converted or hosted here. FIRC reads each line as a `subnet` or `subnet6` rule.
- Updated by upstream about monthly.
- Large lists: `us` holds about 270 000 prefixes and `au` about 160 000; see the note in `loyalsoldier.md`.
- V2Fly's GeoSite (domain-list-community) is already in the catalog as `sagernet`, which compiles it.
- License: CC-BY-SA-4.0. The data is *IP Geolocation by [DB-IP](https://db-ip.com)*, CC-BY-4.0. The catalog only links to it.
