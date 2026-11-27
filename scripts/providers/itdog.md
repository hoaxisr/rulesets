# ITDog

The lists of [itdoginfo/allow-domains](https://github.com/itdoginfo/allow-domains). The catalog links to
the plain lists on its `main` branch; nothing is converted or hosted here.

| id | What | Names |
|---|---|---|
| `itdog-services` | a service's domains (`Services/`) | `discord`, `youtube`, `telegram`, … |
| `itdog-categories` | a category's domains (`Categories/`) | `anime`, `block`, `geoblock`, `news`, … |
| `itdog-ipv4` | a service's IPv4 prefixes (`Subnets/IPv4/`) | `discord`, `telegram`, `meta`, … |
| `itdog-ipv6` | a service's IPv6 prefixes (`Subnets/IPv6/`) | `discord`, `telegram`, `meta`, … |
| `itdog-russia` | `Russia/inside-raw.lst` (blocked inside Russia: all categories and services) and `outside-raw.lst` (Russian sites unavailable from abroad) | `inside`, `outside` |
| `itdog-ukraine` | `Ukraine/inside-raw.lst` | `inside` |

- One service is up to three lists: domains, IPv4, IPv6. Add the ones it needs.
- Every entry of a domain list is a domain suffix (the domain and its subdomains), as ITDog's own sing-box rule-sets read it; FIRC reads a plain line the same way.
- Not taken:
  - the `-clashx`, `-dnsmasq-*`, `-kvas` and `-mikrotik-fwd` variants hold the same domains in other syntaxes;
  - `Subnets/*/Discord.lst`, `Meta.lst` and `Twitter.lst` are capitalised copies the upstream script keeps for old links, byte for byte the lowercase files;
  - `src/` holds the generator's inputs.
- Not used: the SRS files of ITDog's GitHub Releases.
  - They are served from `github.com`, which FIRC's catalog does not allow (`raw.githubusercontent.com` only).
  - Their service rule-sets carry IPv4 prefixes but not IPv6.
  - The plain lists cover the same data with no change to FIRC.
- License: the repository states none, so its lists are linked, never copied.
