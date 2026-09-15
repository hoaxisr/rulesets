#!/usr/bin/env python3
"""awg-manager patches over upstream vernette/rulesets data.

Idempotent: safe to run on every upstream sync. Each patch adds our data on
top of the freshly-synced upstream json/ — upstream files are taken wholesale,
then this script re-applies the awg-manager deltas.

A patch key is `add_<field>`; the values are appended to every rule that
already carries `<field>`, so a patch never invents a new rule shape.
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
    # hoaxisr/rulesets#1: Gemini opens but cannot send messages unless the
    # punctual/multi-watch signalling channel goes through the same proxy.
    "json/gemini.json": {
        "add_domain_suffix": ["signaler-pa.clients6.google.com"],
    },
}


def patch_file(path, spec):
    with open(path) as f:
        data = json.load(f)
    changed = False
    for rule in data.get("rules", []):
        for key, values in spec.items():
            field = key[len("add_"):]
            if field not in rule:
                continue
            for v in values:
                if v not in rule[field]:
                    rule[field].append(v)
                    changed = True
    if changed:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
    return changed


def main():
    for path, spec in PATCHES.items():
        try:
            print(f"patched {path}" if patch_file(path, spec) else f"{path}: already patched")
        except FileNotFoundError:
            print(f"WARNING: {path} missing upstream", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
