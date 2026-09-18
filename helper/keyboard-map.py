#!/usr/bin/env python3
# file generated with AI assistance: Claude Code - 2026-09-16 01:10:00 UTC
#
# Builds ONE JSON document for the Shortkeyz overlay: which board, its
# keys, the bindings per modifier level, the group colours and the
# character levels of every key.
#
# All the domain and parsing logic lives here, not in QML. That's not a
# matter of taste: Quickshell can't read TOML, and `groups.toml` is the
# source of the group colours -- a second copy of the ~50 manual
# assignments is exactly the one you'd forget to update on the next new
# shortcut.
#
# Everything this script knows about bindings and groups lives next to it
# in `hyprkeys.py`. The plugin therefore depends on no file outside its own
# directory -- a requirement for distributing it as a git repo. The one
# exception is `schmunk42-keybindings-doc`: it tracks which binding on this
# particular machine is changed, custom, or re-registered unchanged. That
# is naturally nothing generic, and without the file the column is simply
# left blank.
#
# Usage:
#   keyboard-map [--board ID] [--pretty] [--check] [--list-boards]
#   keyboard-map --new-board [--device NAME] [--id ID] [--stdout]
#   keyboard-map --new-board --generic [--stdout]
#   keyboard-map --list-devices

import argparse
import datetime
import glob
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys

# `realpath`, not `abspath`: the helper is invoked through the symlink
# `~/.local/bin/schmunk42-shortkeyz` on the author's machine. `abspath`
# doesn't resolve that, and the plugin directory would then be `~/.local`
# -- the shipped boards would be invisible, without anything failing.
HERE = os.path.dirname(os.path.realpath(__file__))
PLUGIN = os.path.dirname(HERE)

# NO __pycache__ next to the module: any file that appears in the plugin
# directory triggers Omarchy's inotify reload of the plugin -- the helper
# would reload itself on its very first run.
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import hyprkeys  # noqa: E402  -- only after sys.path
import boardgen  # noqa: E402

HOME = os.path.expanduser("~")

# The user's own boards first, the shipped ones after. A user board with
# the same id wins, so the default can be corrected without touching the
# plugin directory -- anything written there triggers a plugin reload.
BOARD_DIRS = (
    os.path.join(HOME, ".config/schmunk42-shortkeyz/boards"),
    os.path.join(PLUGIN, "defaults/boards"),
)

# The attribution column for this particular machine. If it's missing, the
# column stays blank.
DOC = os.path.join(HOME, ".local/bin/schmunk42-keybindings-doc")

# Bound, but deliberately without a place on a board: mouse buttons, the
# wheel, and the lid switch. They land in `unplaced` and show up there as
# the overflow list, instead of silently disappearing.
NOT_A_KEY = re.compile(r"^(mouse:|mouse_|switch:)")

# First-level keysym -> bit in Hyprland's modmask. Same numbers that
# `hyprctl binds` reports.
MODIFIER_BITS = {
    "Shift_L": 1, "Shift_R": 1,
    "Control_L": 4, "Control_R": 4,
    "Alt_L": 8, "Alt_R": 8, "Meta_L": 8, "Meta_R": 8,
    "Super_L": 64, "Super_R": 64,
    "ISO_Level3_Shift": 128, "ISO_Level5_Shift": 128,
}

# The level names of a four-level type. The keymap only names them for
# keys with an explicit `type=`; these apply to the normal case.
DEFAULT_LEVEL_NAMES = ("Base", "Shift", "AltGr", "Shift+AltGr")


def log(message):
    print(message, file=sys.stderr)


def load_module(path, name):
    """Load a script without a `.py` extension as a module -- the same
    trick schmunk42-keybindings-doc already uses for the daemon."""
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------

def usb_present(vendor, product):
    """Looks for a USB device via sysfs. A generalisation of
    cherry_hidraw() in the LED daemon; `lsusb` isn't installed on the
    author's machine."""
    for path in glob.glob("/sys/bus/usb/devices/*/idVendor"):
        directory = os.path.dirname(path)
        try:
            with open(path) as handle:
                if handle.read().strip().lower() != vendor.lower():
                    continue
            with open(os.path.join(directory, "idProduct")) as handle:
                if handle.read().strip().lower() == product.lower():
                    return True
        except OSError:
            continue
    return False


def dmi_product():
    try:
        with open("/sys/class/dmi/id/product_name") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def board_present(board):
    """Is this keyboard currently attached?

    Two paths, because a built-in keyboard can't take the first: a USB
    device is found by vendor and product id, a laptop's keyboard cannot
    be -- it hangs off the AT controller and is named the same on every
    laptop. For it, the machine itself counts, via the mainboard's DMI
    identifier."""
    match = board.get("match") or {}
    hidraw = match.get("hidraw") or {}
    vendor, product = hidraw.get("vendor"), hidraw.get("product")
    if vendor and product and usb_present(vendor, product):
        return True
    wanted = (match.get("dmi") or {}).get("product")
    if wanted:
        return wanted.lower() in dmi_product().lower()
    return False


def load_boards(warnings):
    """Boards from every directory, the first one wins per id."""
    boards = []
    seen = set()
    for directory in BOARD_DIRS:
        for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
            try:
                with open(path) as handle:
                    board = json.load(handle)
            except (OSError, json.JSONDecodeError) as error:
                warnings.append(
                    f"board unreadable: {os.path.basename(path)}: {error}")
                continue
            if board.get("id") in seen:
                continue
            seen.add(board.get("id"))
            board["_path"] = path
            board["_shipped"] = directory != BOARD_DIRS[0]
            board["present"] = board_present(board)
            boards.append(board)
    return boards


def pick_board(boards, wanted, warnings):
    if wanted:
        for board in boards:
            if board.get("id") == wanted:
                return board
        warnings.append(f"no board {wanted!r}")
        return None
    for board in boards:
        if board["present"]:
            return board
    for board in boards:
        if board.get("fallback") and not board.get("generic"):
            return board
    # The generic board last: it fits every ISO keyboard and none of them
    # exactly. It must never come before a hand-made board.
    for board in boards:
        if board.get("generic"):
            return board
    return boards[0] if boards else None


# ---------------------------------------------------------------------------
# Keymap
# ---------------------------------------------------------------------------

KEY_LINE = re.compile(r'^\s*key\s+<(?P<name>[A-Z0-9+\-]+)>\s*\{')

# Two notations, and the second is a trap. On one line, the symbol list
# sits right behind the opening brace:
#     key <ESC>  {  [ Escape ] };
# On several lines -- for any key with its own type or its own actions --
# it sits behind `symbols[1]=`:
#     symbols[1]= [ ssharp, question, backslash, questiondown, SSHARP ]
# A plain `\[([^\]]*)\]` there matches the **index** bracket `[1]` instead
# and returns the symbol list ["1"]. That is exactly what moved `ssharp`
# from <AE11> onto the fourth level of <AC02>, where an ssharp happens to
# sit too -- and because the hit looked plausible, the bug only shows up if
# you read the level along with it.
SYMBOL_ASSIGN = re.compile(r"symbols\[\d+\]\s*=\s*\[(?P<body>[^\]]*)\]")
SYMBOL_INLINE = re.compile(r"\{\s*\[(?P<body>[^\]]*)\]")
TYPE_HEAD = re.compile(r'^\s*type\s+"(?P<name>[^"]+)"\s*\{')
LEVEL_NAME = re.compile(r'^\s*level_name\[(?P<index>\d+)\]\s*=\s*"(?P<name>[^"]*)"')
KEY_TYPE = re.compile(r'^\s*type\s*=\s*"(?P<name>[^"]+)"')
# The keycode mapping from the `xkb_keycodes` section: `<AE07> = 16;`. The
# equals sign right after the angle bracket tells it apart from the symbol
# section's `key <AE07> { … }` lines.
KEYCODE_LINE = re.compile(r"^\s*<(?P<name>[A-Z0-9+\-]+)>\s*=\s*(?P<code>\d+);")


def read_keymap(warnings):
    """The keymap that's ACTUALLY loaded, not `compile-keymap`.

    The difference is measured and silent: `xkbcli compile-keymap --layout
    de --options …` returns a different result for this machine's own
    option than the running compositor does. Taking the CLI as ground
    truth describes a keyboard that runs nowhere like that."""
    try:
        raw = subprocess.run(["xkbcli", "dump-keymap-wayland"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        warnings.append(f"keymap unreadable: {error}")
        return {}, {}
    if raw.returncode != 0:
        warnings.append(f"xkbcli dump-keymap-wayland: exit {raw.returncode}")
        return {}, {}
    return parse_keymap(raw.stdout)


def parse_keymap(text):
    """(types, keys) from the text of an xkb keymap. Pure, so it can be
    tested against a checked-in dump without a Wayland session."""
    types = {}
    keys = {}
    current_type = None
    current_key = None

    for line in text.splitlines():
        head = TYPE_HEAD.match(line)
        if head:
            current_type = head.group("name")
            types.setdefault(current_type, {})
            continue

        level = LEVEL_NAME.match(line)
        if level and current_type:
            types[current_type][int(level.group("index"))] = level.group("name")
            continue

        code = KEYCODE_LINE.match(line)
        if code:
            entry = keys.setdefault(code.group("name"),
                                    {"symbols": [], "type": None})
            entry["code"] = int(code.group("code"))
            continue

        key = KEY_LINE.match(line)
        if key:
            current_key = key.group("name")
            keys.setdefault(current_key, {"symbols": [], "type": None})

        if current_key:
            key_type = KEY_TYPE.match(line)
            if key_type:
                keys[current_key]["type"] = key_type.group("name")
            # Depending on the key, the symbol list sits on the `key` line
            # itself, or -- for keys with their own type and actions -- on
            # a separate `symbols[1]= [ … ]` line further down.
            if not keys[current_key]["symbols"] and "actions" not in line:
                found = SYMBOL_ASSIGN.search(line) or SYMBOL_INLINE.search(line)
                if found:
                    keys[current_key]["symbols"] = [
                        part.strip() for part in found.group("body").split(",")
                        if part.strip()]
            if line.rstrip().endswith("};"):
                current_key = None

    return types, keys


def level_names(type_name, types, count):
    table = types.get(type_name or "", {})
    names = []
    for index in range(1, count + 1):
        if index in table:
            names.append(table[index])
        elif index <= len(DEFAULT_LEVEL_NAMES):
            names.append(DEFAULT_LEVEL_NAMES[index - 1])
        else:
            names.append(f"Level {index}")
    return names


def build_symbol_index(keys, types, board_keys, aliases):
    """Keysym (lower-case) -> (XKB name, level name or None).

    **The order is the whole trick.** Hyprland reports `Q`, `RETURN`,
    `PRINT` upper-case; the keymap has `q` on level 1 and `Q` on level 2.
    Searching for an exact match first lands every letter on level 2 and
    labels 26 keys "with Shift" -- wrong, and invisible from the outside.

    So: first the board's own Fn-row secondary mapping, then level 1
    case-insensitively, only then the higher levels.
    """
    index = {}

    # 1) What the board itself says about its Fn row
    for entry in board_keys:
        fn = entry.get("fnSym")
        if fn:
            index.setdefault(fn.lower(), (entry["xkb"], "Fn"))

    # Board order, not a set: two keys can share a level-1 keysym (on the
    # author's machine <CAPS> is Control_L, and so is <LCTL>), and with a
    # set the winner would depend on hash seeding. In list order the board
    # file decides -- the earlier entry wins.
    placed = []
    for entry in board_keys:
        if entry["xkb"] not in placed:
            placed.append(entry["xkb"])

    # 2) Level 1 of every key on the board
    for name in placed:
        symbols = keys.get(name, {}).get("symbols") or []
        if symbols:
            index.setdefault(symbols[0].lower(), (name, None))

    # 3) Levels 2..n
    for name in placed:
        info = keys.get(name, {})
        symbols = info.get("symbols") or []
        names = level_names(info.get("type"), types, len(symbols))
        for position, symbol in enumerate(symbols[1:], start=1):
            index.setdefault(symbol.lower(), (name, names[position]))

    # 4) The daemon's aliases (esc -> escape, altgr -> iso_level3_shift)
    for alias, target in aliases.items():
        if target.lower() in index:
            index.setdefault(alias.lower(), index[target.lower()])

    return index


# ---------------------------------------------------------------------------
# Bindings
# ---------------------------------------------------------------------------

def modifier_label(modmask, order, none_label="No modifier"):
    parts = [name for mask, name in order if modmask & mask]
    return " + ".join(parts) if parts else none_label


def level_sort_key(modmask):
    """By number of bits set, then by value -- an order that stays put.
    Sorting by frequency would be more convenient and wrong: it jumps the
    moment you add a binding, and a tab that keeps changing its position
    is worthless as a tab."""
    return (bin(modmask).count("1"), modmask)


def source_index(doc, warnings):
    """(modmask, key) -> character for a binding's provenance."""
    table = {}
    marks = (("CHANGED", "⚠️"), ("OWN", "👤"), ("REBOUND", "🔁"))
    # The doc script spells the empty level out ("Ohne Modifier" on the
    # author's machine); it is the one spec that is not a modifier list.
    none_spec = getattr(doc, "NO_MODIFIER", None)
    for attribute, mark in marks:
        for spec, keys in getattr(doc, attribute, {}).items():
            if spec == none_spec:
                modmask = 0
            else:
                parts = [p for p in str(spec).split("+") if p.strip()]
                modmask = hyprkeys.parse_modifiers(parts)
            if modmask is None:
                # Skip rather than attribute to modmask 0: a typo in the doc
                # script would otherwise mark the wrong key on the wrong
                # level, and nobody would see why.
                warnings.append(f"attribution: unknown modifier in {spec!r}")
                continue
            for key in keys:
                table[(modmask, str(key).lower())] = mark
    return table


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

def build(wanted_board):
    warnings = []
    daemon = hyprkeys
    doc = None
    if os.path.exists(DOC):
        try:
            doc = load_module(DOC, "schmunk42_keybindings_doc")
        except Exception as error:      # noqa: BLE001 -- optional, never fatal
            warnings.append(f"attribution column unreadable: {error}")

    boards = load_boards(warnings)
    if not boards:
        warnings.append(f"no board description under {BOARD_DIRS}")
        return {"warnings": warnings}, warnings

    board = pick_board(boards, wanted_board, warnings)
    if board is None:
        return {"warnings": warnings}, warnings

    types, keymap = read_keymap(warnings)
    board_keys = board.get("keys") or []
    symbols = build_symbol_index(keymap, types, board_keys, daemon.ALIASES)

    # Groups plus screen colour. Which file provides them and in which
    # colour space they're stated is decided by hyprkeys.group_rules().
    rules = daemon.group_rules()
    groups = rules["colors"]

    sources = source_index(doc, warnings) if doc else {}

    # The board's keys, enriched with a label and character levels
    keys_out = []
    for entry in board_keys:
        name = entry["xkb"]
        info = keymap.get(name, {})
        sym = info.get("symbols") or []
        names = level_names(info.get("type"), types, len(sym))
        caption = entry.get("label")
        if not caption and sym:
            caption = hyprkeys.KEY_LABELS.get(sym[0], sym[0])
        keys_out.append({
            "xkb": name,
            # The keycode is the key's physical identity and the only
            # reliable way to trace an overlay key event back to a key on
            # the board: Qt resolves `event.key` via the keysym, and that
            # depends on the level -- Caps Lock arrives as Control_L on
            # press and as Caps_Lock on release.
            "code": info.get("code"),
            # Which modifier the key sets, read off the keysym of its
            # first level. This one field is what turns Caps Lock into a
            # Ctrl key, without the QML needing to know anything about
            # this particular machine.
            "mod": MODIFIER_BITS.get(sym[0] if sym else "", 0),
            "x": entry.get("x", 0), "y": entry.get("y", 0),
            "w": entry.get("w", 1), "h": entry.get("h", 1),
            "shape": entry.get("shape"),
            "led": entry.get("led"),
            "fnSym": entry.get("fnSym"),
            "label": caption or name,
            "levels": [{"name": names[i], "text": hyprkeys.KEY_LABELS.get(s, s)}
                       for i, s in enumerate(sym)],
            "inKeymap": bool(sym) or bool(entry.get("noKeymap")),
        })

    # Bindings per level
    levels = {}
    unplaced = []
    binds = daemon.hyprctl("binds")
    if binds is None:
        # Not `or []` and move on: an empty board with no message is the
        # one outcome the overlay must never produce.
        warnings.append("no bindings: hyprctl -j binds gave no answer"
                        " -- is Hyprland running?")
        binds = []
    for bind in binds:
        key = str(bind.get("key") or "")
        if not key:
            continue
        modmask = bind.get("modmask", 0)
        description = str(bind.get("description") or "")
        lower = key.lower()
        lower = daemon.ALIASES.get(lower, lower)
        group = daemon.group_for(modmask, lower, description.lower(), rules)
        record = {
            "key": key,
            "desc": description,
            "group": group,
            "source": sources.get((modmask, lower), ""),
        }

        target = symbols.get(lower)
        if target is None:
            record["reason"] = ("no key" if NOT_A_KEY.match(lower)
                                else "not in keymap")
            record["modmask"] = modmask
            record["level"] = modifier_label(modmask, hyprkeys.MODIFIER_ORDER, "—")
            unplaced.append(record)
            continue

        xkb_name, needs = target
        record["needs"] = needs

        # If the keysym only exists on a higher level, the binding cannot
        # be triggered on this machine and therefore has no place on the
        # board. With `input.resolve_binds_by_sym` off (Omarchy's default)
        # Hyprland compares keycode and modmask, and `SUPER + SHIFT + SLASH`
        # would need the keycode of <AE07> without Shift -- a combination
        # that never occurs on a German layout, where `/` is Shift+7.
        # Measured on 2026-09-08: none of Omarchy's three `slash` bindings
        # ever fires there.
        #
        # Landing on the board here would mean hiding the reachable
        # binding on the same key: `SUPER + 7` showed "Monitor scaling up"
        # instead of the workspace switch, and in the wrong group colour
        # to boot. The keyboard backlighting gets this right already -- it
        # doesn't know `slash` at all.
        if needs:
            record["reason"] = "not reachable"
            record["modmask"] = modmask
            record["level"] = modifier_label(modmask, hyprkeys.MODIFIER_ORDER, "—")
            unplaced.append(record)
            continue

        # A list, not a single binding: one physical key can carry several
        # bindings. Letting the first one win here would silently drop the
        # second, and you'd end up puzzled by a level with fewer bindings
        # than `hyprctl binds` reports.
        levels.setdefault(modmask, {}).setdefault(xkb_name, []).append(record)

    # Even a level whose bindings ALL end up in the overflow list gets an
    # entry. Without this it would drop out of the display entirely, tab
    # and all: `SHIFT` carries five bindings here, all on XF86 keys, and
    # would otherwise show up nowhere -- not as a tab, and not in the
    # overflow list, which only ever shows the selected level's entries.
    for entry in unplaced:
        levels.setdefault(entry["modmask"], {})

    levels_out = []
    for modmask in sorted(levels, key=level_sort_key):
        bucket = levels[modmask]
        placed = sum(len(records) for records in bucket.values())
        rest = sum(1 for entry in unplaced if entry["modmask"] == modmask)
        levels_out.append({
            "modmask": modmask,
            "label": modifier_label(modmask, hyprkeys.MODIFIER_ORDER),
            "count": placed,
            "restCount": rest,
            # What the tab shows: every binding of this level, including
            # the ones in the overflow list. Counting only the placed ones
            # would leave a tab reading "0" even though five bindings hang
            # off it.
            "total": placed + rest,
            "keyCount": len(bucket),
            "keys": bucket,
        })

    # Whatever hyprkeys logged on the way -- a broken groups.toml, a missing
    # Omarchy module, a shortcut that didn't parse -- travels with the
    # document. The overlay only ever sees stdout; stderr would be lost.
    for message in daemon.MESSAGES:
        if message not in warnings:
            warnings.append(message)

    document = {
        "generated": datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "board": {
            "id": board.get("id"), "name": board.get("name"),
            "size": board.get("size"), "present": board["present"],
            "draft": board.get("draft"), "generic": bool(board.get("generic")),
            "keys": keys_out,
        },
        "boards": [{"id": b.get("id"), "name": b.get("name"),
                    "present": b["present"]} for b in boards],
        "groups": groups,
        "sources": {
            "board": board.get("_path"),
            "shippedBoard": bool(board.get("_shipped")),
            "groups": rules.get("source"),
            "colorspace": rules.get("colorspace"),
            "doc": DOC if doc else None,
        },
        "levels": levels_out,
        "unplaced": unplaced,
        "warnings": warnings,
    }
    return document, warnings


# ---------------------------------------------------------------------------
# Check report
# ---------------------------------------------------------------------------

def generic_drift():
    """Has the shipped `generic-pc105` drifted from the reference?

    The file isn't a second source, it's the checked-in output of
    `--new-board --generic`. Correct the reference geometry and forget the
    file, and the two now ship two different geometries -- and neither
    path shows the drift on its own."""
    path = os.path.join(PLUGIN, "defaults/boards/generic-pc105.json")
    try:
        with open(path) as handle:
            shipped = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        return f"unreadable: {error}"
    # No keymap needed: without a device, build() places the whole reference
    # and never looks one up -- reading it would cost an xkbcli call per
    # --check for nothing.
    fresh = boardgen.build({}, stamp="")
    for document in (shipped, fresh):
        document.pop("generatedWith", None)
    if shipped == fresh:
        return ""
    if shipped.get("keys") != fresh.get("keys"):
        return "keys differ, regenerate with --new-board --generic"
    return "header differs, regenerate with --new-board --generic"


def check(document):
    board = document.get("board") or {}
    keys = board.get("keys") or []
    print(f"Board: {board.get('id')} ({board.get('name')})"
          f"{'' if board.get('present') else '  [not attached]'}")

    # Which files were actually read. The lookup order is otherwise
    # invisible, and the first question on an unexpected colour is exactly
    # this: which groups.toml was that?
    provenance = document.get("sources") or {}
    print(f"  board file:  {provenance.get('board') or '—'}")
    print(f"  groups.toml: {provenance.get('groups') or '—'}"
          f"  ({provenance.get('colorspace') or '—'})")
    print(f"  attribution: {provenance.get('doc') or 'not present'}")
    if board.get("draft"):
        print(f"  DRAFT: {board['draft']}")

    bound = sum(level["count"] for level in document.get("levels", []))
    print(f"\nBindings on the board:          {bound}")

    unplaced = document.get("unplaced") or []
    unreachable = [u for u in unplaced if u.get("reason") == "not reachable"]
    other = [u for u in unplaced if u.get("reason") == "no key"]
    real = [u for u in unplaced
            if u.get("reason") not in ("no key", "not reachable")]
    print(f"Bindings with no place:         {len(unplaced)}"
          f"  ({len(real)} keys, {len(other)} mouse/switch,"
          f" {len(unreachable)} not reachable)")
    for entry in real:
        level = entry.get("level", "—")
        print(f"  {level:22} {entry['key']:26} {entry['desc']}")

    # Not a bug, just Omarchy's default on a layout that can't type it --
    # listed only, with no effect on the exit code.
    print(f"\nNot reachable (higher level):    {len(unreachable)}")
    for entry in unreachable:
        level = entry.get("level", "—")
        print(f"  {level:22} {entry['key']:26} {entry['desc']}"
              f"  (needs {entry.get('needs')})")

    blank = [k["xkb"] for k in keys if not k["inKeymap"]]
    print(f"\nKeys with no keymap entry:       {len(blank)}"
          + ("  " + ", ".join(blank) if blank else ""))

    # No binding of a higher level may still be on the board -- they go
    # into the overflow list instead (see the `needs` branch in build()).
    # This line stays as a check: if anything shows up here, that filter
    # has stopped working.
    shifted = []
    shared = []
    for level in document.get("levels", []):
        for name, records in level["keys"].items():
            if len(records) > 1:
                shared.append(f"{name}: "
                              + " / ".join(r["key"] for r in records)
                              + f" ({level['label']})")
            for record in records:
                if record.get("needs"):
                    shifted.append(f"{record['key']} ({record['needs']}, {name})")
    print(f"On the board despite a higher level: {len(shifted)}"
          + ("  " + ", ".join(shifted) if shifted else "  (must be 0)"))

    print(f"Keys with more than one binding: {len(shared)}")
    for entry in shared:
        print(f"  {entry}")

    drift = generic_drift()
    print(f"\nGeneric board up to date:        {'yes' if not drift else 'NO'}"
          + (f"  ({drift})" if drift else ""))

    for warning in document.get("warnings") or []:
        print(f"WARNING: {warning}")

    return 1 if (real or blank or drift or document.get("warnings")) else 0


def stamp():
    now = datetime.datetime.now(datetime.timezone.utc)
    return "helper/keyboard-map.py --new-board - " + now.strftime("%Y-%m-%d %H:%M:%S UTC")


def list_devices():
    found = boardgen.devices()
    if not found:
        log("No input device looks like a keyboard.")
        return 1
    for device in found:
        print(f"  {device['name']:40} {len(device['codes'])} keys"
              f"  ({os.path.basename(os.path.dirname(device['path']))})")
    return 0


def new_board(args):
    """Write a board draft. Written exclusively to
    `~/.config/schmunk42-shortkeyz/boards/` -- never into the plugin, whose
    directory sits under Omarchy's inotify reload."""
    warnings = []
    _, keymap = read_keymap(warnings)
    for warning in warnings:
        log(f"WARNING: {warning}")
    if not keymap:
        return 1

    device = None
    if not args.generic:
        device, error = boardgen.pick_device(args.device)
        if error:
            log(error)
            return 1

    board = boardgen.build(keymap, device=device, board_id=args.id,
                           name=args.name, stamp=stamp())

    if args.stdout:
        json.dump(board, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    path = boardgen.target_path(HOME, board["id"])
    if os.path.exists(path):
        log(f"already exists: {path}")
        log("delete it, or choose a different name with --id.")
        return 1
    boardgen.write(board, path)
    print(f"{path}")
    print(f"  {len(board['keys'])} keys, {board['size']['w']} x"
          f" {board['size']['h']} key units")
    notes = board.get("notes") or {}
    if notes.get("noGeometry"):
        print("  no place in the geometry: "
              + " ".join(notes["noGeometry"]))
    if notes.get("noKeymapName"):
        codes = notes["noKeymapName"]
        print(f"  no keymap name: {len(codes)} evdev codes "
              + " ".join(str(code) for code in codes[:12])
              + (" ..." if len(codes) > 12 else ""))
    # `sys.argv[0]`, not the script's own name: depending on the machine,
    # the helper is invoked through a symlink, through the plugin path, or
    # not at all -- `omarchy plugin add` sets up no command of its own.
    print(f"  Next: {sys.argv[0]} --board {board['id']} --check")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Keyboard map, bindings and group colours as one JSON document.")
    parser.add_argument("--board", help="force this board instead of detecting one")
    parser.add_argument("--pretty", action="store_true", help="indent the output")
    parser.add_argument("--check", action="store_true",
                        help="print a check report instead of JSON, exit 1 on gaps")
    parser.add_argument("--list-boards", action="store_true")
    parser.add_argument("--list-devices", action="store_true",
                        help="keyboards that sysfs reports")
    parser.add_argument("--new-board", action="store_true",
                        help="draft a board from the device's key set")
    parser.add_argument("--generic", action="store_true",
                        help="with --new-board: the generic ISO-105 template")
    parser.add_argument("--device", help="with --new-board: pick the device")
    parser.add_argument("--id", help="with --new-board: id of the draft")
    parser.add_argument("--name", help="with --new-board: display name")
    parser.add_argument("--stdout", action="store_true",
                        help="with --new-board: print instead of writing")
    args = parser.parse_args()

    if args.list_devices:
        return list_devices()
    if args.new_board:
        return new_board(args)

    document, warnings = build(args.board)

    if args.list_boards:
        for entry in document.get("boards") or []:
            mark = "●" if entry["present"] else "○"
            print(f"  {mark} {entry['id']:24} {entry['name']}")
        return 0

    if args.check:
        return check(document)

    json.dump(document, sys.stdout,
              ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    for warning in warnings:
        log(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
