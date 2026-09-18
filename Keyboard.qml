// file generated with AI assistance: Claude Code - 2026-09-16 02:25:00 UTC
//
// Fullscreen overlay that draws a keyboard board and marks the bound
// hotkeys on it. Opened via a Hyprland binding:
//
//     omarchy-shell shell toggle io.github.schmunk42.shortkeyz
//
// The scaffolding follows /usr/share/omarchy/shell/plugins/emojis/Emojis.qml
// -- the same menu tokens, the same open/close/dismiss contract with the
// host.
//
// The display model comes entirely from helper/keyboard-map.py: the
// board, the bindings per modifier level, the group colours, the
// character levels. This file only draws -- the computing and parsing
// happens there.

import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import "Colors.js" as Contrast

Item {
  id: root

  // Wired up by the host (see shell.qml, Instantiator delegate).
  property string omarchyPath: Quickshell.env("OMARCHY_PATH")
  property var shell: null
  property var manifest: null

  property bool opened: false

  // The helper's parsed document.
  property var model: null
  property string loadError: ""
  property bool loading: false

  // The level chosen by hand. Applies whenever no modifier is held.
  property int manualIndex: 0

  // The modmask of the modifiers currently held, 0 if none.
  //
  // That this works at all is the difference between the overlay and the
  // compositor: a Hyprland binding with `release = true` never fires from
  // a physical keyboard on the author's machine (measured 2026-09-10, the
  // release does reach `input.keyboard.key`, the keybind manager ignores
  // it), while Qt gets press and release cleanly -- the window holds
  // exclusive keyboard focus.
  property int liveMask: 0

  // What is shown: the level of the held modifier, otherwise the chosen
  // one.
  readonly property int levelIndex: {
    if (root.liveMask !== 0) {
      for (var i = 0; i < root.levels.length; i++) {
        if (root.levels[i].modmask === root.liveMask)
          return i
      }
    }
    return Math.min(root.manualIndex, Math.max(0, root.levels.length - 1))
  }

  // The helper lives inside the plugin itself. `__sourceDir` is stamped by
  // Omarchy's PluginRegistry onto every manifest -- that's how the plugin
  // finds its own files no matter where it was installed. The fallback is
  // the path `omarchy plugin add` uses; without it, the overlay would be
  // stuck with no model the moment that field is missing.
  readonly property string pluginDir:
    (root.manifest && root.manifest.__sourceDir)
      ? String(root.manifest.__sourceDir)
      : Quickshell.env("HOME") + "/.config/omarchy/plugins/io.github.schmunk42.shortkeyz"

  readonly property string helper: root.pluginDir + "/helper/keyboard-map.py"

  readonly property var levels: root.model && root.model.levels ? root.model.levels : []
  readonly property var level:
    root.levels.length > 0
      ? root.levels[Math.min(root.levelIndex, root.levels.length - 1)] : null

  // The theme's menu tokens. Anyone putting their own colour values here
  // decouples the overlay from the theme -- which is exactly what it must
  // not do.
  readonly property color background: Color.menu.background
  readonly property color foreground: Color.menu.text
  readonly property color scrim: Color.menu.scrim
  readonly property var borderSpec:
    Border.surfaceSpec("menu", "border", Color.menu.border, Math.max(1, Style.space(2)))
  readonly property int contentMargin: Style.spacing.panelPadding

  // Share of the screen height the card takes up. A cheat sheet shouldn't
  // cover the whole screen -- you glance at it while the application
  // behind it stays visible.
  readonly property real heightShare: 0.4

  // Which keys of the board are the active level's modifiers. They're
  // highlighted so the keyboard itself shows which level is currently
  // shown.
  readonly property var activeModifiers: {
    var out = ({})
    var mask = root.level ? root.level.modmask : 0
    if (mask & 64) { out["LWIN"] = true; out["RWIN"] = true }
    if (mask & 4)  { out["LCTL"] = true; out["RCTL"] = true; out["CAPS"] = true }
    if (mask & 8)  { out["LALT"] = true }
    if (mask & 1)  { out["LFSH"] = true; out["RTSH"] = true }
    if (mask & 128) { out["RALT"] = true }
    return out
  }

  // The payload may request a level: `{"level": "SUPER"}`. What's meant
  // is the label as printed on the tab -- so a second binding can later
  // open the overlay directly on a given level.
  function open(payloadJson) {
    root.opened = true
    // Clear up on open: if the overlay closes mid-chord, the release
    // event never arrives and the white border would stay until the next
    // restart. The same kind of stuck state as the level.
    root.heldCodes = ({})
    root.liveMask = 0
    root.reload()

    var payload = {}
    try { payload = JSON.parse(payloadJson || "{}") } catch (e) {}
    root.wantedLevel = String(payload.level || "")
    root.applyWantedLevel()

    Qt.callLater(function () { keyCatcher.forceActiveFocus() })
  }

  property string wantedLevel: ""

  // Set when the payload named a level that doesn't exist. Shown in the
  // status line: `{"level":"SUEPR"}` used to open level 0 without a word.
  property string levelWarning: ""

  function applyWantedLevel() {
    root.levelWarning = ""
    if (root.wantedLevel === "")
      return
    for (var i = 0; i < root.levels.length; i++) {
      if (root.levels[i].label === root.wantedLevel) {
        root.manualIndex = i
        return
      }
    }
    if (root.levels.length > 0)
      root.levelWarning = "no level \"" + root.wantedLevel + "\""
  }

  function close() {
    root.opened = false
    root.heldCodes = ({})
    root.liveMask = 0
  }

  // On self-closing, the host must find out it's closed -- otherwise its
  // `toggle` gets out of sync and the next key press does nothing.
  function dismiss() {
    root.opened = false
    root.heldCodes = ({})
    root.liveMask = 0
    if (root.shell && typeof root.shell.hide === "function")
      root.shell.hide((root.manifest && root.manifest.id) || "io.github.schmunk42.shortkeyz")
  }

  // The host's own `shell toggle` never calls this (it summons, which calls
  // open()); kept for anyone driving the item directly, and it forwards the
  // payload so a level request isn't lost on that path either.
  function toggle(payloadJson) {
    if (root.opened) root.dismiss()
    else root.open(payloadJson || "{}")
  }

  // Rebuilt on every open. The helper measured takes 105 to 142 ms, and
  // `keepLoaded: true` keeps the last call's model -- so the board stands
  // right away and gets swapped once the answer arrives.
  function reload() {
    if (helperProc.running)
      return
    root.loading = true
    helperProc.running = true
  }

  function selectLevel(index) {
    if (root.levels.length === 0)
      return
    var count = root.levels.length
    root.manualIndex = ((index % count) + count) % count
  }

  // Qt modifiers to Hyprland's modmask. Same numbers `hyprctl binds`
  // reports and that MODIFIER_ORDER carries in the docs script.
  function maskFromModifiers(mods) {
    var mask = 0
    if (mods & Qt.MetaModifier) mask |= 64
    if (mods & Qt.ControlModifier) mask |= 4
    if (mods & Qt.AltModifier) mask |= 8
    if (mods & Qt.ShiftModifier) mask |= 1
    if (mods & Qt.GroupSwitchModifier) mask |= 128
    return mask
  }

  // The keys currently held down, as a set of keycodes. Reassigned (never
  // mutated) on every press and release, so QML recomputes the bindings
  // shown on the board.
  property var heldCodes: ({})

  // Keycode -> key on the board. The keycode is the only reliable bridge
  // from the key event to a key: Qt resolves `event.key` via the keysym,
  // and that depends on the level -- Caps Lock arrives as Control_L on
  // press and as Caps_Lock on release.
  //
  // `event.nativeScanCode` is the very same keycode the keymap uses, with
  // no offset: measured on 2026-09-16 -- Tab 23, Shift_L 50, Caps 66,
  // Alt_L 64, AltGr 108, ESC 9, all identical to `xkbcli
  // dump-keymap-wayland`. The laptop's Fn key reports 248 and appears in
  // no keymap; it simply finds no key here.
  readonly property var keyByCode: {
    var out = ({})
    var board = root.model ? root.model.board : null
    var keys = board ? board.keys : null
    if (keys) {
      for (var i = 0; i < keys.length; i++) {
        if (keys[i].code !== undefined && keys[i].code !== null)
          out[keys[i].code] = keys[i]
      }
    }
    return out
  }

  // Which modifier a key event sets. Ask the board first, which knows the
  // first level's keysym -- that's the only reason Caps Lock counts as a
  // Ctrl key here. The Qt key is the fallback for a key the board doesn't
  // carry (a foreign keyboard with no board file of its own).
  function bitForEvent(event) {
    var key = root.keyByCode[event.nativeScanCode]
    if (key && key.mod)
      return key.mod
    return root.bitForKey(event.key)
  }

  // The key's own bit. Needed because `event.modifiers` doesn't yet carry
  // a modifier key's own bit on **press**, but does on release.
  function bitForKey(key) {
    if (key === Qt.Key_Meta || key === Qt.Key_Super_L || key === Qt.Key_Super_R)
      return 64
    if (key === Qt.Key_Control) return 4
    if (key === Qt.Key_Alt) return 8
    if (key === Qt.Key_Shift) return 1
    if (key === Qt.Key_AltGr) return 128
    return 0
  }

  function pressCode(code) {
    var out = ({})
    for (var name in root.heldCodes)
      out[name] = true
    out[code] = true
    root.heldCodes = out
  }

  function releaseCode(code) {
    var out = ({})
    for (var name in root.heldCodes) {
      if (Number(name) !== code)
        out[name] = true
    }
    root.heldCodes = out
  }

  function groupColor(group) {
    var groups = root.model ? root.model.groups : null
    var entry = groups ? groups[group || ""] : undefined
    return entry && entry.screen ? entry.screen : "#9d9d9d"
  }

  Process {
    id: helperProc

    // `timeout` in front so a stuck helper can't take the overlay down
    // with it -- the same discipline davefano.trackpad-plus applies to its
    // own calls. If no answer comes back, the last run's model stays on
    // screen.
    command: ["timeout", "-k", "2", "5", root.helper]

    // Both streams, and the result is read at exit rather than when stdout
    // closes: stderr is where a Python traceback or a `sys.exit(message)`
    // lands, and without it a helper that died before printing JSON showed
    // up as "returned nothing" with no hint why.
    stdout: StdioCollector { id: helperOut; waitForEnd: true }
    stderr: StdioCollector { id: helperErr; waitForEnd: true }

    onExited: function (exitCode, exitStatus) {
      var raw = String(helperOut.text || "").trim()
      var err = String(helperErr.text || "").trim()
      root.loading = false
      if (raw === "") {
        root.loadError = "The helper returned nothing (exit " + exitCode + "): "
                       + (err !== "" ? err.split("\n").pop() : root.helper)
        return
      }
      try {
        root.model = JSON.parse(raw)
        root.loadError = ""
        if (root.manualIndex >= root.levels.length)
          root.manualIndex = 0
        root.applyWantedLevel()
      } catch (e) {
        root.loadError = "Helper output could not be parsed: " + e
                       + (err !== "" ? " -- " + err.split("\n").pop() : "")
      }
    }
  }

  PanelWindow {
    id: panel

    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"

    WlrLayershell.namespace: "schmunk42-shortkeyz"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    // Without this line, the board lands on the first output instead of
    // the one being looked at. Omarchy's own overlays never set `screen`
    // -- a centred card forgives that, a fullscreen board does not, since
    // its whole sizing depends on the monitor's resolution.
    //
    // Going through the name is necessary: a `HyprlandMonitor` has **no**
    // `screen` property, the direct route returns `undefined` and Qt
    // drops the binding with "Unable to assign [undefined] to
    // QuickshellScreenInfo*". Omarchy takes the same route
    // (`focusedScreenName()` in plugins/bar/Bar.qml).
    //
    // Falling back to the first output isn't a cosmetic shortcut, it's
    // necessary: as long as Hyprland hasn't reported a focused monitor
    // yet, any other answer is `undefined`, and Qt drops the binding with
    // a warning instead of evaluating it again later.
    screen: {
      var screens = Quickshell.screens
      if (!screens || screens.length === 0)
        return null
      var monitor = Hyprland.focusedMonitor
      var name = monitor ? String(monitor.name || "") : ""
      for (var i = 0; i < screens.length; i++) {
        if (screens[i].name === name)
          return screens[i]
      }
      return screens[0]
    }

    Rectangle {
      anchors.fill: parent
      color: root.scrim
    }

    MouseArea {
      anchors.fill: parent
      onClicked: root.dismiss()
    }

    BorderSurface {
      id: card

      // Anchored to the bottom rather than centred: what you're looking
      // something up on shouldn't be hidden by the card sitting on top of
      // it.
      anchors {
        bottom: parent.bottom
        horizontalCenter: parent.horizontalCenter
        bottomMargin: Style.gapsOut
      }

      // The card takes the available space, the board centres itself
      // inside it. The other way round -- card follows content, content
      // follows card -- would be a binding loop: `unit` depends on the
      // remaining area, which would then depend on `unit` again.
      width: panel.width - Style.gapsOut * 2
      height: Math.round(panel.height * root.heightShare)
      radius: Style.cornerRadius

      // **Opaque, not theme-faithfully translucent.** The theme's menu
      // surface sits at 0.92 opacity, and that's exactly right for a
      // small, centred card over a wallpaper. A board taking up half the
      // screen width, by contrast, sits over terminals and editors -- the
      // eight percent of see-through text would make every key label
      // unreadable. Hue and border stay the theme's; only the alpha
      // channel is pulled to 1.
      color: Qt.rgba(root.background.r, root.background.g, root.background.b, 1.0)
      borderSpec: root.borderSpec
      padding: root.contentMargin

      // Swallows clicks so that a hit on the card doesn't register as
      // "clicked outside" on the scrim and close the overlay.
      MouseArea { anchors.fill: parent; onClicked: {} }

      Item {
        id: keyCatcher

        anchors.fill: parent
        anchors.margins: card.contentTopInset
        focus: true

        Keys.priority: Keys.BeforeItem

        // Release first: otherwise the level would stay stuck on the
        // last modifier held, and the board would show something that no
        // longer applies.
        Keys.onReleased: function (event) {
          root.releaseCode(event.nativeScanCode)

          var bit = root.bitForEvent(event)
          if (bit !== 0) {
            root.liveMask = root.maskFromModifiers(event.modifiers) & ~bit
            event.accepted = true
          }
        }

        Keys.onPressed: function (event) {
          root.pressCode(event.nativeScanCode)

          // A held modifier switches the level for as long as it's held
          // -- the same display the Cherry gives, just with labels.
          var bit = root.bitForEvent(event)
          if (bit !== 0) {
            root.liveMask = root.maskFromModifiers(event.modifiers) | bit
            event.accepted = true
            return
          }

          // As long as a modifier is held, any other key is part of a
          // chord, not navigation inside the overlay.
          if (root.liveMask !== 0) {
            root.liveMask = root.maskFromModifiers(event.modifiers)
            event.accepted = true
            return
          }

          // The switch keys are deliberately bare keys: Hyprland bindings
          // pass right through the overlay, and a key with a binding on
          // modmask 0 would trigger both at once. Free here are Tab, the
          // digits and the arrow keys -- modmask 0 only ever carries XF86
          // keys, PRINT, F9 and the two lid switches.
          if (event.key === Qt.Key_Escape) {
            root.dismiss()
            event.accepted = true
          } else if (event.key === Qt.Key_Tab) {
            root.selectLevel(root.levelIndex + 1)
            event.accepted = true
          } else if (event.key === Qt.Key_Backtab) {
            root.selectLevel(root.levelIndex - 1)
            event.accepted = true
          } else if (event.key === Qt.Key_Right || event.key === Qt.Key_Down) {
            root.selectLevel(root.levelIndex + 1)
            event.accepted = true
          } else if (event.key === Qt.Key_Left || event.key === Qt.Key_Up) {
            root.selectLevel(root.levelIndex - 1)
            event.accepted = true
          } else if (event.key >= Qt.Key_1 && event.key <= Qt.Key_9) {
            root.selectLevel(event.key - Qt.Key_1)
            event.accepted = true
          } else if (event.key === Qt.Key_0) {
            root.selectLevel(9)
            event.accepted = true
          } else if (event.key === Qt.Key_R) {
            root.reload()
            event.accepted = true
          }
        }

        // ------------------------------------------------------------------
        // Header: level tabs
        // ------------------------------------------------------------------
        Flow {
          id: tabs

          anchors { top: parent.top; left: parent.left; right: parent.right }
          spacing: Style.spacing.xs

          Repeater {
            model: root.levels

            delegate: Rectangle {
              id: tab

              required property var modelData
              required property int index

              readonly property bool current: root.levelIndex === tab.index

              radius: Style.cornerRadius
              color: tab.current ? Color.menu.selectedBackground : "transparent"
              border.color: tab.current ? Color.menu.selectedBorder
                            : Qt.rgba(Color.menu.text.r, Color.menu.text.g,
                                      Color.menu.text.b, 0.16)
              border.width: 1
              implicitWidth: tabLabel.implicitWidth + Style.spacing.md
              implicitHeight: tabLabel.implicitHeight + Style.spacing.xs

              Text {
                id: tabLabel
                anchors.centerIn: parent
                // `total`, not `count`: otherwise the SHIFT tab would read
                // 0 even though five bindings hang off it -- they all sit
                // on XF86 keys and end up in the overflow list.
                text: tab.modelData.label + "  " + tab.modelData.total
                color: tab.current ? Color.menu.selectedText : Color.menu.text
                opacity: tab.current ? 1.0 : 0.62
                font.family: Style.font.menuFamily
                font.pixelSize: Style.font.caption
              }

              MouseArea {
                anchors.fill: parent
                onClicked: root.manualIndex = tab.index
              }
            }
          }
        }

        // ------------------------------------------------------------------
        // The board
        // ------------------------------------------------------------------
        Item {
          id: boardArea

          anchors {
            top: tabs.bottom
            bottom: rest.top
            left: parent.left
            right: parent.right
            topMargin: Style.spacing.md
            bottomMargin: Style.spacing.xs
          }

          Board {
            id: boardItem

            anchors.centerIn: parent
            board: root.model ? root.model.board : null
            bindings: root.level ? root.level.keys : ({})
            groups: root.model ? root.model.groups : ({})
            activeModifiers: root.activeModifiers
            heldCodes: root.heldCodes

            // Width is used up fully, height is whatever remains.
            // Capped above so the board doesn't grow absurdly large on a
            // very wide screen.
            unitX: {
              var size = root.model && root.model.board
                         ? root.model.board.size : null
              if (!size || !size.w)
                return 0
              return Math.min(Style.space(150), boardArea.width / size.w)
            }
            unitY: {
              var size = root.model && root.model.board
                         ? root.model.board.size : null
              if (!size || !size.h)
                return 0
              return Math.min(Style.space(110), boardArea.height / size.h)
            }
          }
        }

        // ------------------------------------------------------------------
        // Overflow list: what has no key on this board
        // ------------------------------------------------------------------
        // One line, no more. It used to wrap over four lines on "No
        // modifier" and take away exactly the space the board is there
        // for. The full content is a nice-to-have anyway -- anyone who
        // needs it reads it via `helper/keyboard-map.py --check`.
        Text {
          id: rest

          anchors { bottom: legend.top; left: parent.left; right: parent.right
                    bottomMargin: Style.spacing.xs / 2 }
          elide: Text.ElideRight
          color: root.foreground
          opacity: 0.55
          font.family: Style.font.menuFamily
          font.pixelSize: Style.font.caption

          readonly property var entries: {
            if (!root.model || !root.model.unplaced || !root.level)
              return []
            var out = []
            for (var i = 0; i < root.model.unplaced.length; i++) {
              var entry = root.model.unplaced[i]
              if (entry.modmask === root.level.modmask)
                out.push(entry)
            }
            return out
          }

          // The line always stays in place, even with no entry: were it
          // to disappear, the board would shift down a line and back up
          // again on every level switch -- and the very picture you're
          // trying to compare would jump. The space character holds the
          // line height; empty text would have none.
          height: implicitHeight

          text: {
            // Two kinds in one line: keys this board doesn't have (the
            // XF86 row), and bindings whose keysym on the German layout
            // only exists on a higher level and can therefore never be
            // triggered. The second kind is named explicitly, or you'd go
            // looking for it on the board.
            if (rest.entries.length === 0)
              return " "
            var names = []
            for (var i = 0; i < rest.entries.length; i++) {
              var entry = rest.entries[i]
              names.push(entry.key
                         + (entry.reason === "not reachable"
                            ? " (not reachable)" : ""))
            }
            return "Not on the board (" + names.length + "):  "
                 + names.join(" · ")
          }
        }

        // ------------------------------------------------------------------
        // Footer: group legend and the detail line
        // ------------------------------------------------------------------
        Row {
          id: legend

          anchors { bottom: parent.bottom; left: parent.left }
          spacing: Style.spacing.xs

          Repeater {
            model: {
              if (!root.model || !root.model.groups)
                return []
              var out = []
              for (var name in root.model.groups) {
                if (name !== "")
                  out.push(name)
              }
              out.sort()
              out.push("")
              return out
            }

            delegate: Rectangle {
              id: swatchBox

              required property var modelData

              readonly property color swatch: root.groupColor(swatchBox.modelData)

              radius: Style.cornerRadius
              color: swatchBox.swatch
              implicitWidth: swatchLabel.implicitWidth + Style.spacing.md
              implicitHeight: swatchLabel.implicitHeight + Style.spacing.xs

              // The colour carries the full fill here, so the text is
              // chosen by contrast -- unlike on the keys, where it sits
              // under 0.22 opacity and stays `Color.menu.text`.
              Text {
                id: swatchLabel
                anchors.centerIn: parent
                text: swatchBox.modelData === "" ? "no group" : swatchBox.modelData
                color: Contrast.contrastInk(swatchBox.swatch)
                font.family: Style.font.menuFamily
                font.pixelSize: Style.font.caption
              }
            }
          }
        }

        Text {
          id: detail

          anchors { bottom: parent.bottom; left: legend.right; right: parent.right
                    leftMargin: Style.spacing.md }
          elide: Text.ElideRight
          color: root.foreground
          opacity: root.loadError !== "" ? 1.0 : 0.72
          font.family: Style.font.menuFamily
          font.pixelSize: Style.font.bodySmall

          // A fixed line instead of a floating tooltip: scanning a
          // keyboard while searching sweeps across the whole area, and a
          // tooltip hopping around over the neighbouring keys would hide
          // exactly what you're trying to compare.
          text: {
            if (root.loadError !== "")
              return root.loadError
            if (root.loading && !root.model)
              return "loading …"
            if (!root.model)
              return "no model"

            var board = root.model.board
            // The generic board is nobody's keyboard -- it fits every
            // ISO-105 and none of them exactly. Whoever sees it has no
            // board of their own yet, and the way to get one belongs on
            // the same line -- as a path into this plugin, not as
            // `schmunk42-shortkeyz`: that name only exists on the
            // author's machine, `omarchy plugin add` sets up no command
            // of its own. The hint is tied to the board, not to
            // `shippedBoard`: a shipped board that matches this exact
            // device is correct and needs no hint.
            var head = (board ? board.name : "")
                     + (board && board.generic
                        ? "  ·  your own board:  " + root.helper + " --new-board"
                        : (board && !board.present ? "  (not attached)" : ""))

            // Whatever the helper could not do -- no hyprctl answer, an
            // unreadable board file, a groups.toml that didn't parse -- is
            // said here, ahead of the hints. A partial result that looks
            // like a whole one is the failure this overlay must not have.
            var warnings = root.model.warnings || []
            var problems = []
            if (root.levelWarning !== "")
              problems.push(root.levelWarning)
            for (var w = 0; w < warnings.length; w++)
              problems.push(warnings[w])
            if (problems.length > 0)
              return "⚠ " + problems.join("  ·  ") + "   ·   " + head

            if (boardItem.hoveredKey === "")
              return head + "   ·   Tab switches level, R reloads, Esc closes"

            var records = root.level ? (root.level.keys[boardItem.hoveredKey] || []) : []
            if (records.length === 0)
              return head + "   ·   " + boardItem.hoveredKey + " — no binding"

            var parts = []
            for (var i = 0; i < records.length; i++) {
              var r = records[i]
              parts.push((root.level.label === "No modifier"
                          ? "" : root.level.label + " + ")
                         + r.key
                         + (r.needs ? " (" + r.needs + ")" : "")
                         + " — " + r.desc
                         + (r.group ? "  [" + r.group + "]" : ""))
            }
            return parts.join("   ·   ")
          }
        }
      }
    }
  }
}
