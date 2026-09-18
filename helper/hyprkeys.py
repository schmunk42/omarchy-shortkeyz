# file generated with AI assistance: Claude Code - 2026-09-16 20:38:26 UTC
#
# What this plugin needs to know about Hyprland's bindings, without anything
# that only holds on one particular machine.
#
# The logic here started life in ~/.local/bin/schmunk42-keyboard-color, the
# Cherry keyboard backlight daemon on the author's machine -- that's where it
# was written, but the wrong place for it: it only ever reads files every
# Omarchy install has (the binding modules under /usr/share/omarchy) and a
# groups.toml. The daemon, by contrast, drives LEDs over hidraw and is bound
# to one specific device.
#
# As long as both copies run side by side they can drift apart, and the
# overlay and the keyboard backlighting would then show different groups.
# The next step is therefore to let the daemon import this module and keep
# its own copy only as a fallback.

import json
import os
import re
import subprocess
import sys

try:
    import tomllib
except ModuleNotFoundError:
    # Python < 3.11. Stop here rather than "carry on without groups.toml":
    # the file would be skipped, the colour space would fall back to LED,
    # and the defaults would get converted a second time -- three silent
    # wrongs that look like a working overlay with odd colours.
    sys.exit("shortkeyz: Python 3.11 or newer is required (tomllib)")

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
HOME = os.path.expanduser("~")

OMARCHY_PATH = os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")

# The local machine's file first, then the shipped one. The first is also
# the keyboard backlighting's file -- that way the overlay and the LEDs show
# the same groups, and that agreement is the best check there is for this.
GROUPS_FILES = (
    os.path.join(HOME, ".config/schmunk42-shortkeyz/groups.toml"),
    os.path.join(HOME, ".config/schmunk42-keyboard-color/groups.toml"),
    os.path.join(PLUGIN, "defaults/groups.toml"),
)

# The boost the LED daemon applies to its colours: an LED behind a milky
# keycap swallows colour. It is here only so it can be undone again -- see
# unboost().
SATURATION = float(os.environ.get("SCHMUNK_KEYBOARD_SATURATION", "1.5"))
VALUE = float(os.environ.get("SCHMUNK_KEYBOARD_VALUE", "1.3"))

# Hyprland reports some keys under a different name than the keymap uses.
# Both names point at the same physical key.
ALIASES = {
    "esc": "escape",
    "enter": "return",
    "kp_enter": "return",
    "pgup": "prior",
    "page_up": "prior",
    "pgdn": "next",
    "page_down": "next",
    "del": "delete",
    "caps": "caps_lock",
    "altgr": "iso_level3_shift",
    "alt_r": "iso_level3_shift",
    "super": "super_l",
    "shift": "shift_l",
    "control": "control_l",
    "ctrl": "control_l",
    "alt": "alt_l",
}

# Display text for the keysyms whose name differs from the character
# actually printed on a German keyboard layout. This is layout data, not UI
# text -- it reflects what is physically on the key, so it stays as written
# regardless of interface language.
KEY_LABELS = {
    "dead_circumflex": "^", "ssharp": "ß", "dead_acute": "´",
    "udiaeresis": "ü", "odiaeresis": "ö", "adiaeresis": "ä",
    "plus": "+", "numbersign": "#", "comma": ",", "period": ".",
    "minus": "-", "less": "<",
}

# 128 is MOD5 -- the level ISO_Level3_Shift hangs off, i.e. AltGr. Hyprland
# calls it MOD5; this is the name a reader actually sees on the keyboard.
MODIFIER_ORDER = ((64, "SUPER"), (4, "CTRL"), (8, "ALT"), (1, "SHIFT"),
                  (128, "ALTGR"))

MODIFIER_MASKS = {name: mask for mask, name in MODIFIER_ORDER}

# Modifier names as they may appear in groups.toml and in the attribution
# script. One vocabulary for both: the strict parser below rejects anything
# else, and "altgr" used to be missing here while the attribution script
# spelled its level exactly that way -- ALTGR + P silently lost its mark.
MODIFIER_NAMES = {
    "shift": 1, "ctrl": 4, "control": 4, "strg": 4,
    "alt": 8, "mod1": 8, "super": 64, "win": 64, "mod4": 64,
    "altgr": 128, "mod5": 128,
}

# Where the classification comes from: the file that defines the binding.
# `hyprctl binds` doesn't say *what* a binding does -- the dispatcher for
# every Lua binding is "__lua" with a running number as its argument. The
# description is therefore the only feature available, and the group isn't
# encoded in its wording but in which Omarchy module the binding lives in.
CATEGORY_SOURCES = {
    "apps": (OMARCHY_PATH + "/default/hypr/bindings/applications.lua",),
    "clipboard": (OMARCHY_PATH + "/default/hypr/bindings/clipboard.lua",),
}

# Descriptions to classify beyond what the files above cover, lower-cased,
# matched verbatim. Deliberately empty: a description of one's own binding
# belongs in the user's groups.toml under [shortcuts], not in shipped code
# -- the one entry that used to sit here went stale the moment its binding
# was reworded, and nobody noticed because it simply stopped matching.
EXTRA_CATEGORIES = {}

# Contains "workspace" but isn't navigation.
NOT_WORKSPACE = frozenset({"toggle workspace layout"})

# Navigation is recognised by wording, not by file: it is spread across
# several modules.
WORKSPACE_WORD = re.compile(r"workspace", re.IGNORECASE)

# First argument of o.bind is the key, second is the description.
BIND_DESCRIPTION = re.compile(r'o\.bind\(\s*"[^"]*"\s*,\s*"([^"]*)"')

# Built-in colours, in SCREEN values -- the same five the shipped
# groups.toml carries, and exactly unboost() of the LED daemon's defaults
# (#ff1400, #00ff28, #ffd000, #0080ff, #ff7800, #cccccc). They are never run
# through unboost() again, whatever colour space a groups.toml declares:
# only values read from a file are in that file's space.
DEFAULT_GROUP_COLORS = {
    "apps": "#c44c41",
    "navigation": "#41c456",
    "clipboard": "#c4ac41",
    "layout": "#4183c4",
    "special": "#c47f41",
}
DEFAULT_UNGROUPED = "#9d9d9d"


# Everything log() reports, in order. keyboard-map.py copies this list into
# the document's `warnings`, so a broken groups.toml or a missing Omarchy
# module reaches the overlay's status line and not only stderr -- which the
# shell's Process would otherwise have to collect separately.
MESSAGES = []


def log(message):
    MESSAGES.append(message)
    print("shortkeyz: " + message, file=sys.stderr, flush=True)


def hyprctl(*args):
    """`hyprctl -j …` as parsed JSON, or None -- and None is logged.

    Silent None was the worst hole in this module: with Hyprland not
    reachable, the overlay drew a board with zero bindings and no message,
    indistinguishable from a machine with no bindings."""
    try:
        done = subprocess.run(["hyprctl", "-j", *args], capture_output=True,
                              timeout=5, text=True)
    except (OSError, subprocess.SubprocessError) as error:
        log(f"hyprctl {' '.join(args)}: {error}")
        return None
    if done.returncode != 0:
        log(f"hyprctl {' '.join(args)}: exit {done.returncode}"
            f" {done.stderr.strip()}")
        return None
    try:
        return json.loads(done.stdout)
    except ValueError as error:
        log(f"hyprctl {' '.join(args)}: not JSON: {error}")
        return None


def parse_hex(token):
    token = str(token or "").lstrip("#")
    if len(token) != 6:
        return None
    try:
        return tuple(int(token[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def hexcolor(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def unboost(rgb, saturation_factor=SATURATION, value_factor=VALUE):
    """The inverse of the boost applied by the LED daemon.

    `#ff1400` is unbearable as a full fill on a screen. The calculation
    uses the same model as the daemon, not HSV: every channel is expressed
    by its distance from the brightest one, and that distance is preserved
    -- which is why the hue doesn't shift.

    The inverse is exact as long as the boost didn't clip. Where it did,
    the result is the brightest colour that would have produced the same
    boosted value; that is good enough for display purposes.
    """
    hi, lo = max(rgb), min(rgb)
    if hi <= 0:
        return (0, 0, 0)

    saturation = min(1.0, (hi - lo) / hi / saturation_factor)
    peak = min(255.0, hi / value_factor)

    out = []
    for channel in rgb:
        share = (hi - channel) / (hi - lo) if hi > lo else 0.0
        out.append(max(0, min(255, round(peak * (1 - saturation * share)))))
    return tuple(out)


def parse_modifiers(parts):
    """["super", "ctrl"] -> 68. None as soon as one part isn't a modifier.

    None rather than "skip the unknown part": a typo like "STRG + V" must
    not quietly become modmask 0 and land on the wrong line of the map."""
    modmask = 0
    for part in parts:
        bit = MODIFIER_NAMES.get(str(part).strip().lower())
        if bit is None:
            return None
        modmask |= bit
    return modmask


def parse_shortcut(spec):
    """"SUPER + CTRL + V" -> (68, "v"). None if the last part is missing."""
    parts = [part.strip().lower() for part in str(spec).split("+")]
    parts = [part for part in parts if part]
    if not parts:
        return None

    modmask = parse_modifiers(parts[:-1])
    if modmask is None:
        return None

    key = parts[-1]
    return (modmask, ALIASES.get(key, key))


def categories():
    """Group -> set of descriptions, lower-cased.

    Workspace navigation is not in this table: it is recognised in
    category_for() by wording, because it is spread across several files."""
    table = {}
    for name, paths in CATEGORY_SOURCES.items():
        found = set(EXTRA_CATEGORIES.get(name, ()))
        for path in paths:
            try:
                with open(path) as handle:
                    text = handle.read()
            except OSError as error:
                log(f"group {name} has no source: {error}")
                continue
            found.update(hit.lower() for hit in BIND_DESCRIPTION.findall(text))
        table[name] = found
    return table


def category_for(description, table):
    if not description:
        return None
    for name, known in table.items():
        if description in known:
            return name
    if description in NOT_WORKSPACE:
        return None
    if WORKSPACE_WORD.search(description):
        return "navigation"
    return None


def groups_file():
    """The first existing file from GROUPS_FILES, or None."""
    for path in GROUPS_FILES:
        if os.path.exists(path):
            return path
    return None


def group_rules():
    """Everything needed to classify a binding.

      colors     group name -> {led, screen} as hex
      overrides  (modmask, key) -> group name or None, from [shortcuts]
      auto       the groups inferred from Omarchy's modules
      source     which groups.toml was read
      colorspace "led" or "screen"

    The colour space decides whether the file's values need to be
    converted back for the screen. Without it, "led" applies: the local
    machine's file belongs to the keyboard backlighting and carries LED
    values. The shipped file says `colorspace = "screen"` and is taken as
    written.

    An empty group name in [shortcuts] means "no group", explicitly.
    """
    rules = {"colors": {}, "overrides": {}, "auto": categories(),
             "source": None, "colorspace": "led"}

    # name -> (hex, colour space). The built-ins are screen values; whatever
    # the file contributes is in the file's declared space. Keeping the
    # space per value is the whole point: a "screen" file that leaves one
    # group unnamed must not get that group's default pushed through
    # unboost(), and an LED file must not get the defaults left un-converted.
    raw = {name: (token, "screen") for name, token in DEFAULT_GROUP_COLORS.items()}
    ungrouped = (DEFAULT_UNGROUPED, "screen")
    config = {}

    path = groups_file()
    if path:
        rules["source"] = path
        try:
            with open(path, "rb") as handle:
                config = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as error:
            log(f"{path}: {error}")
            config = {}

    meta = config.get("meta") or {}
    rules["colorspace"] = str(meta.get("colorspace") or "led").strip().lower()
    if rules["colorspace"] not in ("led", "screen"):
        log(f"{path}: [meta] colorspace = {rules['colorspace']!r}"
            " is neither \"led\" nor \"screen\", assuming led")
        rules["colorspace"] = "led"

    for name, token in (config.get("groups") or {}).items():
        if parse_hex(token):
            raw[str(name).strip().lower()] = (str(token), rules["colorspace"])
        else:
            log(f"{path}: [groups] {name} = {token!r} is not a colour")
    if parse_hex(meta.get("ungrouped")):
        ungrouped = (str(meta["ungrouped"]), rules["colorspace"])

    for name, (token, space) in list(raw.items()) + [("", ungrouped)]:
        rgb = parse_hex(token)
        if space == "screen":
            rules["colors"][name] = {"led": None, "screen": hexcolor(rgb)}
        else:
            rules["colors"][name] = {"led": hexcolor(rgb),
                                     "screen": hexcolor(unboost(rgb))}

    for spec, name in (config.get("shortcuts") or {}).items():
        parsed = parse_shortcut(spec)
        if parsed is None:
            log(f"{path}: [shortcuts] {spec!r} could not be parsed")
            continue
        name = str(name or "").strip().lower()
        if name and name not in rules["colors"]:
            log(f"{path}: group {name!r} has no colour in [groups]")
            continue
        rules["overrides"][parsed] = name or None

    return rules


def group_for(modmask, key, description, rules):
    if (modmask, key) in rules["overrides"]:
        return rules["overrides"][(modmask, key)]
    return category_for(description, rules["auto"])
