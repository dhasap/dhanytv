#!/usr/bin/env python3
"""Verify and fix ClearKey keys in dhanytv.m3u.

Searches BOTH backwards and forwards from each EXTINF for the
associated license_key line, then replaces with correct value.

Usage: python3 verify_keys.py dhanytv.m3u
"""
import re
import sys

CORRECT = {
    "FUBO SPORTS 1": "dc69b6159a0f9f0a4e03b3ff91cbacd5:d0dcbcd7723bc40df0bf34c9c092d51f",
    "FUBO SPORTS 2": "3dcfbec0e7146928baa55210bf2cb62f:bc85f74f815d9be5ae1dd6defaa05135",
    "Disney Channel": "be9caaa813c5305e761c66ac63645901:3d40f2e87e2e6e4d201b845b2bb4b8c0",
    "TSN 1": "3dcfbec0e7146928baa55210bf2cb62f:bc85f74f815d9be5ae1dd6defaa05135",
    "SportTV 1": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98",
    "TNT SPORTS 1": "e03f302ec4dabcccca82cc9f76731ec9:53ea1027d2bf2893a552cf15bc0366de",
    "beIN Sports 1": "335dad778109954503dcbb21dc92015f:24bfd75d436cbf73168a2a2dccd40281",
    "TSN SPORTS 1": "14eeabf30c14b7fbf3008c03099ce011:17d2ac8dbc5429bd70af3433aa12158d",
}


def main() -> int:
    filepath = sys.argv[1] if len(sys.argv) > 1 else "dhanytv.m3u"
    with open(filepath) as f:
        lines = f.read().split("\n")

    fixed = 0
    for i, line in enumerate(lines):
        if not line.strip().startswith("#EXTINF"):
            continue
        m = re.search(r",(.+)$", line)
        if not m:
            continue
        name = m.group(1).strip()
        if name not in CORRECT:
            continue

        correct = CORRECT[name]

        # Search BACKWARDS
        for j in range(i - 1, max(i - 20, -1), -1):
            prev = lines[j].strip()
            if prev.startswith("#EXTINF") or (not prev.startswith("#") and prev):
                break
            if "license_key=" in prev and "http" not in prev.split("license_key=", 1)[1][:10]:
                current_key = prev.split("license_key=", 1)[1].strip()
                if current_key != correct:
                    lines[j] = lines[j].replace(current_key, correct)
                    fixed += 1
                    print(f"FIXED: {name}")
                break
        else:
            # Search FORWARDS
            for j in range(i + 1, min(i + 15, len(lines))):
                nxt = lines[j].strip()
                if nxt.startswith("#EXTINF") or nxt.startswith("http"):
                    break
                if "license_key=" in nxt and "http" not in nxt.split("license_key=", 1)[1][:10]:
                    current_key = nxt.split("license_key=", 1)[1].strip()
                    if current_key != correct:
                        lines[j] = lines[j].replace(current_key, correct)
                        fixed += 1
                        print(f"FIXED: {name}")
                    break

    if fixed > 0:
        with open(filepath, "w") as f:
            f.write("\n".join(lines))
        print(f"\n{fixed} keys fixed in {filepath}")
    else:
        print("\nAll keys correct ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
