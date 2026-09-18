# file generated with AI assistance: Claude Code - 2026-09-18 15:10:00 UTC
#
# Unit tests for the pure parts of the helper -- everything that needs no
# Wayland session, no Hyprland and no hardware. The keymap fixture is a real
# `xkbcli dump-keymap-wayland` from the author's machine (German layout with
# a custom Caps-as-Ctrl option): it carries the two traps the parser was
# written against -- `symbols[1]=` on a separate line, and a keysym that
# exists on two keys at different levels.
#
# Run from the repository root:
#
#     python3 -B -m unittest discover -s tests -v
#
# `-B`, because a __pycache__ inside the plugin directory triggers Omarchy's
# plugin reload when the tests run on an installed copy.

import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, "helper")
sys.path.insert(0, HELPER)

import boardgen  # noqa: E402
import hyprkeys  # noqa: E402


def load_keyboard_map():
    """keyboard-map.py has a hyphen in its name, so no plain import."""
    loader = importlib.machinery.SourceFileLoader(
        "keyboard_map", os.path.join(HELPER, "keyboard-map.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


km = load_keyboard_map()

with open(os.path.join(ROOT, "tests/fixtures/keymap-de-schmunk42.xkb")) as _f:
    KEYMAP_TEXT = _f.read()
TYPES, KEYS = km.parse_keymap(KEYMAP_TEXT)


class ParseKeymap(unittest.TestCase):

    def test_keycodes_come_from_the_keycodes_section(self):
        self.assertEqual(KEYS["AE07"]["code"], 16)
        self.assertEqual(KEYS["CAPS"]["code"], 66)
        self.assertEqual(KEYS["ESC"]["code"], 9)

    def test_symbols_on_a_separate_line_are_not_the_index_bracket(self):
        # `symbols[1]= [ ssharp, ... ]` -- a naive `\[(.*?)\]` grabs the "[1]".
        self.assertEqual(KEYS["AE11"]["symbols"][0], "ssharp")
        self.assertEqual(KEYS["AE11"]["type"], "FOUR_LEVEL_PLUS_LOCK")

    def test_a_key_with_actions_keeps_its_symbols(self):
        # The custom Caps key: symbols and actions on separate lines.
        self.assertEqual(KEYS["CAPS"]["symbols"], ["Control_L", "Caps_Lock"])

    def test_inline_symbols(self):
        self.assertEqual(KEYS["ESC"]["symbols"], ["Escape"])

    def test_level_names_for_a_named_type(self):
        names = km.level_names("FOUR_LEVEL_PLUS_LOCK", TYPES, 5)
        self.assertEqual(names[0], "Base")
        self.assertEqual(len(names), 5)


class SymbolIndex(unittest.TestCase):

    BOARD = [{"xkb": "AC02"}, {"xkb": "AE11"}, {"xkb": "AD01"},
             {"xkb": "CAPS"}, {"xkb": "LCTL"}, {"xkb": "AE07"}]

    def index(self, board=None):
        return km.build_symbol_index(KEYS, TYPES, board or self.BOARD,
                                     hyprkeys.ALIASES)

    def test_upper_case_from_hyprctl_lands_on_level_one(self):
        # Hyprland says "Q"; the keymap has q on level 1 and Q on level 2.
        # Level 1 must win, or 26 letters read "with Shift".
        self.assertEqual(self.index()["q"], ("AD01", None))

    def test_ssharp_is_the_level_one_key_not_the_level_four_one(self):
        # AC02 (the letter s) carries ssharp on its fourth level too.
        self.assertEqual(self.index()["ssharp"], ("AE11", None))

    def test_slash_only_exists_on_a_higher_level(self):
        xkb, needs = self.index()["slash"]
        self.assertEqual(xkb, "AE07")
        self.assertIsNotNone(needs)

    def test_shared_level_one_keysym_is_resolved_in_board_order(self):
        # CAPS and LCTL are both Control_L on this keymap. The board file
        # decides, deterministically -- not a set's iteration order.
        first_caps = self.index([{"xkb": "CAPS"}, {"xkb": "LCTL"}])
        first_lctl = self.index([{"xkb": "LCTL"}, {"xkb": "CAPS"}])
        self.assertEqual(first_caps["control_l"][0], "CAPS")
        self.assertEqual(first_lctl["control_l"][0], "LCTL")

    def test_aliases_follow_their_target(self):
        index = self.index()
        self.assertEqual(index["ctrl"], index["control_l"])


class Shortcuts(unittest.TestCase):

    def test_parse_shortcut(self):
        self.assertEqual(hyprkeys.parse_shortcut("SUPER + CTRL + V"), (68, "v"))
        self.assertEqual(hyprkeys.parse_shortcut("ALTGR + P"), (128, "p"))
        self.assertEqual(hyprkeys.parse_shortcut("SUPER + ENTER"), (64, "return"))

    def test_unknown_modifier_is_an_error_not_modmask_zero(self):
        self.assertIsNone(hyprkeys.parse_shortcut("SUEPR + V"))
        self.assertIsNone(hyprkeys.parse_modifiers(["super", "strgg"]))

    def test_parse_modifiers(self):
        self.assertEqual(hyprkeys.parse_modifiers([]), 0)
        self.assertEqual(hyprkeys.parse_modifiers(["SUPER", " Shift "]), 65)


class Colours(unittest.TestCase):

    LED = {"apps": "#ff1400", "navigation": "#00ff28", "clipboard": "#ffd000",
           "layout": "#0080ff", "special": "#ff7800", "": "#cccccc"}

    def test_unboost_of_led_defaults_gives_the_screen_defaults(self):
        for name, led in self.LED.items():
            want = hyprkeys.DEFAULT_GROUP_COLORS.get(name, hyprkeys.DEFAULT_UNGROUPED)
            self.assertEqual(hyprkeys.hexcolor(hyprkeys.unboost(hyprkeys.parse_hex(led))),
                             want, name)

    def rules_for(self, toml_text):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "groups.toml")
            with open(path, "w") as handle:
                handle.write(toml_text)
            saved = hyprkeys.GROUPS_FILES
            hyprkeys.GROUPS_FILES = (path,)
            try:
                return hyprkeys.group_rules()
            finally:
                hyprkeys.GROUPS_FILES = saved

    def test_screen_file_leaving_a_group_unnamed_keeps_the_default_as_is(self):
        rules = self.rules_for('[meta]\ncolorspace = "screen"\n'
                               '[groups]\napps = "#112233"\n')
        self.assertEqual(rules["colors"]["apps"]["screen"], "#112233")
        # `layout` is not in the file: the built-in screen value, untouched.
        self.assertEqual(rules["colors"]["layout"]["screen"],
                         hyprkeys.DEFAULT_GROUP_COLORS["layout"])

    def test_led_file_values_are_converted_and_defaults_are_not(self):
        rules = self.rules_for('[groups]\napps = "#ff1400"\n')
        self.assertEqual(rules["colorspace"], "led")
        self.assertEqual(rules["colors"]["apps"], {"led": "#ff1400", "screen": "#c44c41"})
        self.assertEqual(rules["colors"]["layout"],
                         {"led": None, "screen": hyprkeys.DEFAULT_GROUP_COLORS["layout"]})

    def test_broken_toml_is_reported_not_swallowed(self):
        before = len(hyprkeys.MESSAGES)
        rules = self.rules_for('[groups\napps = "#112233"\n')
        self.assertGreater(len(hyprkeys.MESSAGES), before)
        self.assertEqual(rules["colors"]["apps"]["screen"],
                         hyprkeys.DEFAULT_GROUP_COLORS["apps"])


class Boards(unittest.TestCase):

    def test_parse_bitmap(self):
        # The TUXEDO's internal keyboard, verbatim from
        # /sys/class/input/event3/device/capabilities/key (153 keys).
        codes = boardgen.parse_bitmap(
            "10000 0 0 0 402000007 ff803078f800d001 feffffdfffcfffff fffffffffffffffe")
        self.assertEqual(len(codes), 153)
        for code in boardgen.REQUIRED_CODES:   # ESC, Q, A, Space
            self.assertIn(code, codes)
        self.assertIn(58, codes)     # Caps Lock
        self.assertNotIn(0, codes)   # KEY_RESERVED, the low bit of the last word
        self.assertNotIn(200, codes)
        self.assertEqual(boardgen.parse_bitmap("1"), {0})
        self.assertEqual(boardgen.parse_bitmap("1 0"), {64})

    def test_reference_keys_do_not_overlap(self):
        keys = boardgen.reference()
        boxes = [(k["xkb"], k["x"], k["x"] + k.get("w", 1),
                  k["y"], k["y"] + k.get("h", 1)) for k in keys]
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                overlap = a[1] < b[2] and b[1] < a[2] and a[3] < b[4] and b[3] < a[4]
                # The ISO Enter's bounding box reaches over BKSL; its polygon
                # doesn't. Everything else must be disjoint.
                if {a[0], b[0]} == {"RTRN", "BKSL"}:
                    continue
                self.assertFalse(overlap, f"{a[0]} overlaps {b[0]}")

    def test_shipped_generic_board_matches_the_reference(self):
        with open(os.path.join(ROOT, "defaults/boards/generic-pc105.json")) as handle:
            shipped = json.load(handle)
        fresh = boardgen.build({}, stamp="")
        for document in (shipped, fresh):
            document.pop("generatedWith", None)
        self.assertEqual(shipped, fresh)

    def test_device_draft_places_only_reported_keys(self):
        device = {"name": "Test", "codes": {1, 16, 30, 57},  # ESC Q A Space
                  "bustype": "0011", "vendor": "0001", "product": "0001"}
        board = boardgen.build(KEYS, device=device, stamp="")
        self.assertEqual({k["xkb"] for k in board["keys"]},
                         {"ESC", "AD01", "AC01", "SPCE"})
        self.assertFalse(board["generic"])


if __name__ == "__main__":
    unittest.main()
