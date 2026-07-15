#!/usr/bin/env python3
"""awg-manager patches over upstream vernette/rulesets data.

Idempotent: safe to run on every upstream sync. Each patch adds our data on
top of the freshly-synced upstream json/ — upstream files are taken wholesale,
then this script re-applies the awg-manager deltas.
"""
import json
import sys

PATCHES = {
    # awg-manager#534 context: Discord voice needs the extra CDN CIDR and the
    # newer voice port range on top of upstream data.
    "json/discord-full.json": {
        "add_ip_cidr": ["104.29.0.0/16"],
        "add_port_range": ["19200:19400"],
    },
}


def patch_discord(path, spec):
    with open(path) as f:
        data = json.load(f)
    changed = False
    for rule in data.get("rules", []):
        if "ip_cidr" not in rule:
            continue
        for cidr in spec["add_ip_cidr"]:
            if cidr not in rule["ip_cidr"]:
                rule["ip_cidr"].append(cidr)
                changed = True
        if "port_range" in rule:
            for pr in spec["add_port_range"]:
                if pr not in rule["port_range"]:
                    rule["port_range"].append(pr)
                    changed = True
    if changed:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
    return changed


def main():
    any_changed = False
    for path, spec in PATCHES.items():
        try:
            if patch_discord(path, spec):
                print(f"patched {path}")
                any_changed = True
            else:
                print(f"{path}: already patched")
        except FileNotFoundError:
            print(f"WARNING: {path} missing upstream", file=sys.stderr)
    return 0 if True else 1


if __name__ == "__main__":
    sys.exit(main())
