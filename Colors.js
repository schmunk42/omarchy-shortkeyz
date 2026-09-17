// file generated with AI assistance: Claude Code - 2026-09-16 02:05:00 UTC
//
// WCAG 2.x contrast math. Carried over from
// ~/.config/omarchy/plugins/schmunk42.workspaces/Workspaces.qml (the
// functions srgbChannel, relLum, contrastRatio, contrastInk there) --
// checked against Omarchy's `Commons/`, which has nothing like it.
//
// Needed wherever a group colour sits as a full-strength fill: in the
// legend and on the level tabs. Not on the keys themselves, because there
// the colour sits at 0.22 opacity under the label and the label stays
// `Color.menu.text` throughout -- a board with shifting label colour reads
// as noisy.

.pragma library

function srgbChannel(v) {
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
}

// The difference from plain brightness is the gamma correction: without
// it, mid-dark colours come out too light.
function relLum(c) {
    return 0.2126 * srgbChannel(c.r)
         + 0.7152 * srgbChannel(c.g)
         + 0.0722 * srgbChannel(c.b)
}

function contrastRatio(a, b) {
    var la = relLum(a)
    var lb = relLum(b)
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

// Whichever of black/white contrasts better against `bg`. White on a tie.
function contrastInk(bg) {
    var white = Qt.rgba(1, 1, 1, 1)
    var black = Qt.rgba(0, 0, 0, 1)
    return contrastRatio(white, bg) >= contrastRatio(black, bg) ? white : black
}
