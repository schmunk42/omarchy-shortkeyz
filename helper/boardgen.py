#!/usr/bin/env python3
# file generated with AI assistance: Claude Code - 2026-09-17 17:10:00 UTC
#
# Generate board drafts: the key set the device itself reports, laid out on
# a generic ISO-105 geometry.
#
# What is and isn't possible here is measured, not assumed: WHICH keys a
# keyboard has, it says itself via `/sys/class/input/event*/device/capabilities/key`
# -- world-readable, no `input` group needed. WHERE those keys sit, no
# system source says: `xkeyboard-config` has neither TUXEDO nor Clevo, and
# the keymap describes meanings, not positions. The result is therefore a
# *draft*: the set is correct, the geometry is guessed.
#
# The reference below is the complete ISO-105 keyboard. Both boards come
# from it -- the shipped `generic-pc105`, by placing everything, and a
# device draft, by placing only what the device reports. A laptop loses its
# numpad this way, on its own.

import glob
import json
import os
import re

# The reference's rows: (y, x-start, [(XKB name, width, extras)]). Within a
# row the widths add up -- two keys of the same row can therefore never
# overlap, and only the row starts and the F-row's gaps are written by
# hand.
_AE = [(f"AE{i:02d}", 1) for i in range(1, 13)]
_AD = [(f"AD{i:02d}", 1) for i in range(1, 13)]
_AC = [(f"AC{i:02d}", 1) for i in range(1, 12)]
_AB = [(f"AB{i:02d}", 1) for i in range(1, 11)]

# The ISO keyboard's Enter key is L-shaped: 1.5 wide at the top (AD row),
# only 1.25 at the bottom (AC row) -- the notch sits at the bottom left,
# because the AC row carries one more key with BKSL. The polygon is given
# in key units relative to the top-left corner.
_RTRN_SHAPE = [[0, 0], [1.5, 0], [1.5, 2], [0.25, 2], [0.25, 1], [0, 1]]

ROWS = (
    (0, 0.0, [("ESC", 1)]),
    (0, 2.0, [("FK01", 1), ("FK02", 1), ("FK03", 1), ("FK04", 1)]),
    (0, 6.5, [("FK05", 1), ("FK06", 1), ("FK07", 1), ("FK08", 1)]),
    (0, 11.0, [("FK09", 1), ("FK10", 1), ("FK11", 1), ("FK12", 1)]),
    (0, 15.25, [("PRSC", 1), ("SCLK", 1), ("PAUS", 1)]),

    (1, 0.0, [("TLDE", 1)] + _AE + [("BKSP", 2)]),
    (1, 15.25, [("INS", 1), ("HOME", 1), ("PGUP", 1)]),
    (1, 18.5, [("NMLK", 1), ("KPDV", 1), ("KPMU", 1), ("KPSU", 1)]),

    (2, 0.0, [("TAB", 1.5)] + _AD
             + [("RTRN", 1.5, {"h": 2, "shape": _RTRN_SHAPE})]),
    (2, 15.25, [("DELE", 1), ("END", 1), ("PGDN", 1)]),
    (2, 18.5, [("KP7", 1), ("KP8", 1), ("KP9", 1), ("KPAD", 1, {"h": 2})]),

    (3, 0.0, [("CAPS", 1.75)] + _AC + [("BKSL", 1)]),
    (3, 18.5, [("KP4", 1), ("KP5", 1), ("KP6", 1)]),

    (4, 0.0, [("LFSH", 1.25), ("LSGT", 1)] + _AB + [("RTSH", 2.75)]),
    (4, 16.25, [("UP", 1)]),
    (4, 18.5, [("KP1", 1), ("KP2", 1), ("KP3", 1), ("KPEN", 1, {"h": 2})]),

    (5, 0.0, [("LCTL", 1.25), ("LWIN", 1.25), ("LALT", 1.25), ("SPCE", 6.25),
              ("RALT", 1.25), ("RWIN", 1.25), ("MENU", 1.25), ("RCTL", 1.25)]),
    (5, 15.25, [("LEFT", 1), ("DOWN", 1), ("RGHT", 1)]),
    (5, 18.5, [("KP0", 2), ("KPDL", 1)]),
)

# Without these four keys, an input device isn't a keyboard: the evdev
# codes of ESC, Q, A and Space. The filter drops mice, power buttons, lid
# switches and the consumer-control interfaces that every second keyboard
# registers on top.
REQUIRED_CODES = (1, 16, 30, 57)

# Keymap names of the form `<I172>`: just the evdev code spelled out
# differently.
SYNTHETIC_NAME = re.compile(r"^I\d+$")

# The keymap's X keycode minus the evdev code. Measured: `<CAPS> = 66` in
# the keymap, `KEY_CAPSLOCK` is 58.
EVDEV_OFFSET = 8


def reference():
    """The complete ISO-105 geometry as a flat key list."""
    keys = []
    for row in ROWS:
        y, x = row[0], row[1]
        for entry in row[2]:
            name, width = entry[0], entry[1]
            extras = entry[2] if len(entry) > 2 else {}
            key = {"xkb": name, "x": round(x, 3), "y": y}
            if width != 1:
                key["w"] = width
            key.update(extras)
            keys.append(key)
            x += width
    return keys


def parse_bitmap(text):
    """evdev bitmap from sysfs: 64-bit words, least significant last."""
    codes = set()
    for index, word in enumerate(reversed(text.split())):
        value = int(word, 16)
        base = index * 64
        while value:
            lowest = value & -value
            codes.add(base + lowest.bit_length() - 1)
            value ^= lowest
    return codes


def _read(path):
    try:
        with open(path) as handle:
            return handle.read().strip()
    except OSError:
        return ""


def devices():
    """Every input device that passes as a keyboard."""
    found = []
    for path in sorted(glob.glob("/sys/class/input/event*/device")):
        bitmap = _read(os.path.join(path, "capabilities/key"))
        if not bitmap:
            continue
        codes = parse_bitmap(bitmap)
        if not all(code in codes for code in REQUIRED_CODES):
            continue
        found.append({
            "name": _read(os.path.join(path, "name")) or os.path.basename(path),
            "path": path,
            "codes": codes,
            "bustype": _read(os.path.join(path, "id/bustype")),
            "vendor": _read(os.path.join(path, "id/vendor")),
            "product": _read(os.path.join(path, "id/product")),
        })
    return _fold(found)


def _fold(found):
    """One device, one row.

    A USB keyboard routinely reports several interfaces under the same
    name -- the Cherry here reports three. Choosing by name is then
    impossible, even though there is only one keyboard.

    Folding happens by device id, and the key sets are **unioned**, not
    picked: the interfaces aren't subsets of one another, they complement
    each other. For the Cherry, one interface reports 252 keys without a
    single modifier, the other 163 including them -- taking the larger one
    gives a draft with no Ctrl, Shift, Alt or Super."""
    folded = {}
    for device in found:
        key = (device["bustype"], device["vendor"], device["product"],
               device["name"])
        if key in folded:
            folded[key]["codes"] |= device["codes"]
            continue
        folded[key] = dict(device, codes=set(device["codes"]))
    return sorted(folded.values(), key=lambda d: d["name"])


def pick_device(wanted):
    """Exactly one device or an error message -- never a guess.

    Anyone with two keyboards would otherwise get a draft for the wrong
    one that looks plausible and isn't. That is worse than no draft at
    all."""
    found = devices()
    if not found:
        return None, "No input device looks like a keyboard."
    if wanted:
        needle = wanted.lower()
        hits = [d for d in found if needle in d["name"].lower()]
        if not hits:
            names = ", ".join(repr(d["name"]) for d in found)
            return None, f"No device matches {wanted!r}. Available: {names}"
        if len(hits) > 1:
            names = ", ".join(repr(d["name"]) for d in hits)
            return None, f"{wanted!r} matches more than one: {names}"
        return hits[0], None
    if len(found) > 1:
        names = ", ".join(repr(d["name"]) for d in found)
        return None, ("Several keyboards -- which one? Choose with --device: "
                      + names)
    return found[0], None


def slug(text):
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value or "board"


def build(keymap, device=None, board_id=None, name=None, stamp=""):
    """Board draft. Without `device`, the complete reference."""
    codes = None
    if device is not None:
        codes = device["codes"]

    placed, no_geometry = [], []
    for key in reference():
        entry = keymap.get(key["xkb"]) or {}
        code = entry.get("code")
        if codes is None:
            placed.append(key)
            continue
        if code is None or (code - EVDEV_OFFSET) not in codes:
            continue
        placed.append(key)

    board = {
        "schemaVersion": 1,
        "generatedWith": stamp,
        "id": board_id or (slug(device["name"]) if device else "generic-pc105"),
        "name": name or (device["name"] if device else "Generic PC-105 keyboard"),
        # The generic board is the last resort: `fallback` so it applies
        # when nothing was detected, and `generic` so it steps aside for
        # any hand-made board.
        "fallback": device is None,
        "generic": device is None,
    }

    if device is not None:
        # What the device reports and finds no place here. Both are manual
        # work for the user, and both would vanish silently if not listed.
        known = {}
        for xkb, entry in keymap.items():
            code = entry.get("code")
            if code is not None:
                known[code - EVDEV_OFFSET] = xkb
        geometry = {key["xkb"] for key in reference()}
        for code in sorted(codes):
            xkb = known.get(code)
            # `I172` and its siblings aren't names, they're the keymap's
            # fallback spelling for an evdev code with no symbolic name.
            # Naming that helps no one -- the code does.
            if xkb is None or SYNTHETIC_NAME.match(xkb):
                no_geometry.append(code)
            elif xkb not in geometry:
                no_geometry.append(xkb)
        board["draft"] = (
            "Draft from the device's key set, laid out on a generic"
            " ISO-105 geometry. The set is correct, the placement is"
            " guessed: check modifier widths, the Fn row, the right-hand"
            " special keys and the F-keys' secondary function (field"
            " fnSym) against the real device.")
        board["notes"] = {
            "noGeometry": [n for n in no_geometry if isinstance(n, str)],
            "noKeymapName": [n for n in no_geometry if isinstance(n, int)],
        }
        # How this board recognises its keyboard: a USB keyboard by its
        # device id, a built-in one by the machine's DMI product name --
        # it is called "AT Translated Set 2 keyboard" on every laptop.
        if device["bustype"] == "0003" and device["vendor"] and device["product"]:
            board["match"] = {"hidraw": {"vendor": device["vendor"],
                                         "product": device["product"]}}
        else:
            product = _read("/sys/class/dmi/id/product_name")
            if product:
                board["match"] = {"dmi": {"product": product}}
    else:
        board["draft"] = (
            "Generic ISO-105 keyboard, not measured against real hardware."
            " Generate your own board with"
            " `helper/keyboard-map.py --new-board`.")

    width = max(key["x"] + key.get("w", 1) for key in placed)
    height = max(key["y"] + key.get("h", 1) for key in placed)
    board["size"] = {"w": round(width, 3), "h": round(height, 3)}
    board["keys"] = placed
    return board


def target_path(home, board_id):
    return os.path.join(home, ".config/schmunk42-shortkeyz/boards",
                        board_id + ".json")


def write(board, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        json.dump(board, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
