// file generated with AI assistance: Claude Code - 2026-09-16 02:15:00 UTC
//
// Draws a keyboard board from the document that
// helper/keyboard-map.py delivers: each key's XKB name and its position in
// key units, plus the bindings of the currently selected modifier level.
// Pixel size is computed from the available area.
//
// Deliberately without its own colour values for fills and text: those come
// from the theme's menu tokens, so the board inherits the look of the
// Omarchy menu instead of reimplementing it. Only the group colours are
// values of our own, and even those don't live here -- they live in
// groups.toml.

import QtQuick
import QtQuick.Shapes
import qs.Commons

Item {
  id: root

  // The `board` part of the document (id, name, size, keys).
  property var board: null

  // XKB name -> list of bindings for this level. A list, because on the
  // German layout several bindings can share the same physical key:
  // SUPER + 7 and SUPER + SLASH are both <AE07>.
  property var bindings: ({})

  // Group name -> { led, screen }
  property var groups: ({})

  // The modifier keys of the active level, as a set of XKB names.
  property var activeModifiers: ({})

  // The keys currently held down, as a set of keycodes. Keycode rather than
  // XKB name, because the key event only reliably carries the keycode.
  property var heldCodes: ({})

  // Two units instead of one: the board should use the available width
  // rather than being squeezed to the centre at a fixed aspect ratio. With
  // limited height -- the card only takes up part of the screen -- that
  // would otherwise leave a narrow board with a lot of empty space on
  // either side, and the labels would stay tiny even though there is room.
  property real unitX: 60
  property real unitY: 60

  // For anything that doesn't depend on one axis (font sizes, spacing), the
  // smaller of the two counts -- otherwise the text would spill out of a
  // flat key.
  readonly property real unit: Math.min(unitX, unitY)

  property string hoveredKey: ""

  readonly property real gap: Math.max(1, unit * 0.055)
  readonly property real keyRadius: Math.max(2, unit * 0.09)

  implicitWidth: board && board.size ? board.size.w * unitX : 0
  implicitHeight: board && board.size ? board.size.h * unitY : 0

  function recordsFor(name) {
    var found = root.bindings ? root.bindings[name] : undefined
    return found ? found : []
  }

  function groupColor(group) {
    var entry = root.groups ? root.groups[group || ""] : undefined
    return entry && entry.screen ? entry.screen : "#9d9d9d"
  }

  Repeater {
    model: root.board && root.board.keys ? root.board.keys : []

    delegate: Item {
      id: cap

      required property var modelData

      readonly property var records: root.recordsFor(cap.modelData.xkb)
      readonly property var primary: cap.records.length > 0 ? cap.records[0] : null
      readonly property bool bound: cap.primary !== null
      readonly property bool isModifier: !!(root.activeModifiers
                                            && root.activeModifiers[cap.modelData.xkb])
      readonly property bool hovered: root.hoveredKey === cap.modelData.xkb
      readonly property bool held: !!(root.heldCodes
                                      && cap.modelData.code !== undefined
                                      && root.heldCodes[cap.modelData.code])

      readonly property color accent:
        cap.bound ? root.groupColor(cap.primary.group) : Color.menu.text

      // Fill at 0.22, border at full colour -- the same pattern as the
      // workspace badges in the bar: only the border carries the colour
      // unmixed, the fill blends with the background. This is also the
      // answer to how harsh LED colours would be as a full fill.
      readonly property color fillColor:
        cap.bound ? Qt.rgba(cap.accent.r, cap.accent.g, cap.accent.b, 0.22)
        : (cap.isModifier ? Color.menu.selectedBackground : "transparent")
      // A key currently held down gets a full-white border -- the only
      // colour on the board that belongs to no group, and therefore the
      // only one that can't be mistaken for a meaning. Deliberately not
      // `Color.menu.text`: its white is slightly off in the theme and read
      // as too dim next to the group colours.
      readonly property color strokeColor:
        cap.held ? "#ffffff"
        : (cap.bound ? cap.accent
           : (cap.isModifier ? Color.menu.selectedBorder
              : Qt.rgba(Color.menu.text.r, Color.menu.text.g, Color.menu.text.b, 0.18)))

      readonly property real strokeWidth:
        Math.max(1, root.unit * (cap.held ? 0.06 : (cap.bound ? 0.022 : 0.014)))

      // This key's own scale: for a half-height key (Up/Down in the arrow
      // cluster) the key unit is the wrong reference -- the text would run
      // past the edge.
      //
      // NOT `scale`: that already exists on QQuickItem as a scale
      // transform. A property of the same name only shadows it -- until
      // someone animates it and the key grows by a factor of "key edge in
      // pixels". qmllint flags it as a property-override.
      readonly property real keyScale: Math.min(root.unit, cap.height * 0.9)

      clip: true

      x: cap.modelData.x * root.unitX
      y: cap.modelData.y * root.unitY
      width: (cap.modelData.w === undefined ? 1 : cap.modelData.w) * root.unitX
      height: (cap.modelData.h === undefined ? 1 : cap.modelData.h) * root.unitY

      Loader {
        anchors.fill: parent
        anchors.margins: root.gap / 2
        sourceComponent: cap.modelData.shape ? polygonBody : rectangleBody
      }

      // Rectangular key -- the normal case, roughly four out of five keys.
      Component {
        id: rectangleBody

        Rectangle {
          radius: root.keyRadius
          color: cap.fillColor
          border.color: cap.strokeColor
          border.width: cap.strokeWidth
          opacity: cap.hovered ? 1.0 : 0.94
        }
      }

      // Only the ISO Enter key needs this: a polygon relative to the key's
      // corner, in key units.
      Component {
        id: polygonBody

        Shape {
          preferredRendererType: Shape.CurveRenderer

          ShapePath {
            fillColor: cap.fillColor
            strokeColor: cap.strokeColor
            strokeWidth: cap.strokeWidth
            joinStyle: ShapePath.RoundJoin

            // PathPolyline sets its own start point -- an extra
            // startX/startY would draw an edge back to the element's
            // origin.
            PathPolyline {
              path: {
                var pts = []
                for (var i = 0; i < cap.modelData.shape.length; i++)
                  pts.push(Qt.point(cap.modelData.shape[i][0] * root.unitX,
                                    cap.modelData.shape[i][1] * root.unitY))
                pts.push(Qt.point(cap.modelData.shape[0][0] * root.unitX,
                                  cap.modelData.shape[0][1] * root.unitY))
                return pts
              }
            }
          }
        }
      }

      // The label printed on the key itself, small and top-left: what is
      // actually written on the real key. The binding's effect sits below
      // it, centred, and gets the space.
      Text {
        anchors {
          top: parent.top; left: parent.left; right: parent.right
          topMargin: root.gap * 1.6
          leftMargin: root.gap * 2; rightMargin: root.gap * 2
        }
        elide: Text.ElideRight
        text: cap.modelData.label || cap.modelData.xkb
        color: Color.menu.text
        opacity: cap.bound ? 0.75 : 0.42
        font.family: Style.font.menuFamily
        font.pixelSize: Math.max(8, cap.keyScale * 0.24)
      }

      // The effect of the binding. Two lines, then truncated -- the full
      // text shows in the detail line at the bottom of the card on hover.
      Text {
        anchors {
          left: parent.left; right: parent.right
          verticalCenter: parent.verticalCenter
          verticalCenterOffset: root.unit * 0.13
          leftMargin: root.gap * 1.6; rightMargin: root.gap * 1.6
        }
        // Below roughly 34 px of key edge, the effect text is left off and
        // the detail line at the bottom of the card carries it alone -- a
        // board with grey noise on it is worse than one without. The
        // threshold is lower than the number suggests: the panel scales at
        // 1.6, so seven logical pixels are eleven physical ones.
        visible: cap.bound && cap.keyScale >= 30
        text: cap.primary ? cap.primary.desc : ""
        color: Color.menu.text
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        maximumLineCount: 2
        elide: Text.ElideRight
        font.family: Style.font.menuFamily
        font.pixelSize: Math.max(7, cap.keyScale * 0.19)
      }

      // Where the binding came from (changed / own / re-registered
      // unchanged), and the hint that more than one binding sits here.
      Text {
        anchors {
          bottom: parent.bottom; right: parent.right
          bottomMargin: root.gap * 1.4; rightMargin: root.gap * 2
        }
        visible: cap.bound
        text: (cap.primary && cap.primary.source ? cap.primary.source : "")
              + (cap.records.length > 1 ? " +" + (cap.records.length - 1) : "")
        color: Color.menu.text
        opacity: 0.8
        font.family: Style.font.menuFamily
        font.pixelSize: Math.max(6, cap.keyScale * 0.17)
      }

      MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
        onEntered: root.hoveredKey = cap.modelData.xkb
        onExited: if (root.hoveredKey === cap.modelData.xkb) root.hoveredKey = ""
      }
    }
  }
}
