# Common layout-container projection contract

This document specifies a measurement correction for Amendment 4. It is not an
exception list, a reduction in required elements, or a change to matcher
tolerances. The complete raw DOM, UIA/XAML and AX/native paint records remain
auditable. A canonical element represents something actually visible or
independently usable, not every framework object used to implement it.

Implementation status: the accompanying reference change adds only two
previously omitted, independently evidenced region cases described below.
The general cross-platform proof and ownership rules in this document still
need implementation and CI validation. No native wrapper is approved for
removal by this document. Existing coverage failures remain failures.

## Projection decisions

Visibility is evaluated first using actual clipping, opacity, paint order and
occlusion evidence. An unmeasured clip or paint effect is not proof of
invisibility. For each visible candidate, independently determine:

* **Own paint:** does this node own visible text, fill, border, shadow, image,
  path, outline, decoration or another drawing operation?
* **Independent interaction:** does it provide its own focus target, action,
  selection, disclosure, editing, scrolling or other user operation?
* **Independent semantic region:** is it the actual owner of a named
  navigation/content region or other explicit page region, rather than merely
  a descendant assigned to that region?

Each answer is `present`, `absent`, or `unknown`, with references to the
provider's actual raw evidence. Missing values mean `unknown`, not `absent`.
The resulting dispositions are:

| Evidence | Disposition |
| --- | --- |
| Own visible paint is present | Emit the actual painted element or attach its paint to a uniquely proven canonical owner. Preserve all paint sources. |
| Independent interaction or semantic region is present | Emit the control/region even if its fill is transparent. |
| Multiple raw records represent the same actual element | Attach them to one canonical owner only when actual identity/ancestry and ownership prove the relationship. |
| Own paint, interaction and independent semantics are all proven absent | Keep this exact layout node in raw evidence with a proof record; do not emit a duplicate visible element. |
| Any necessary answer or owner relationship is unknown | Preserve raw evidence and a coverage failure. Do not remove an existing canonical element on an unproven layout-only claim. |

The disposition of one node never disposes of its subtree. Continue walking
every child, retain every independent child element, and connect a projected
child to its nearest retained ancestor. Keep source reading order and explicit
raw-to-canonical parent links. Do not merge siblings just because their labels,
sizes, colors or bounding boxes happen to coincide.

## What constitutes proof

`AXGroup`, `AXOpaqueProviderGroup`, `AXScrollArea`, `Grid`, `StackPanel`, `div`
and similar names are not dispositions. Likewise, an empty name, a common
rectangle, `isAccessibilityElement=true`, `IsControlElement=false`, or the
absence of an accessibility child does not establish absence of paint or
interaction. Microsoft's [UI Automation tree
documentation](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-treeoverview)
explicitly distinguishes raw, control and content views. A decoration absent
from the control view is still required by this visual-parity contract.

To certify **no own paint**, measure every applicable paint channel and its
ownership: fill including images/gradients, per-edge borders/strokes, shadows,
outlines, native layer contents, custom draw operations, and actual text or
pseudo content. A known transparent fill only proves the fill contributes no
paint; it says nothing about the border or shadow. A null background, an
unsupported brush, an uninstrumented SwiftUI decoration, or an unresolved
native layer/drawing relationship prevents a no-paint conclusion. An actual
paint ledger can attribute template/surface operations to a real owner; a
source identifier or a manually asserted `layoutOnly` flag is not such a ledger.
Sparse screenshot samples also cannot certify that an entire node is unpainted.

To certify **no independent interaction**, retain actual supported actions,
focusability and relevant native interaction ownership. UIA patterns and
focusability, AX/native action and focus evidence, or actual DOM semantics and
linked AX properties provide positive witnesses. Being unfocused now is not
being unfocusable; a non-Control XAML object may still handle pointer events;
an empty `onclick` property does not rule out delegated DOM listeners. Unknown
event/action ownership must remain unknown. `IsHitTestVisible=true` by itself
does not prove an action, and a role name by itself does not prove its absence.

To certify **no independent semantic region**, distinguish region membership
from region ownership. A production marker assigning child text to
`conversation` is not a new conversation region. Conversely, a real named
navigation landmark, toolbar, menu, dialog or explicit page-area owner must
not disappear just because it paints no background. Repeated identifier
strings do not prove that two objects are the same owner.

For **ownership**, retain the source record identities, the actual owning
object/template relationship, the canonical owner ID, and which properties
are contributed by each source. Owner lookup must be unique; ambiguous
same-size surface matches remain failures. A surface with paint but no proven
semantic owner remains a painted element rather than disappearing. Its kind
should follow its actual role: a painted card does not become a page region
merely because the paint probe inherited a region name.

Each proof record should identify the raw node, its disposition, the three
answers above, the exact raw property/action/paint sources, any canonical
owner, and unresolved measurements. These are required audit contents, not an
instruction to fill missing canonical style/state fields with constants. Each
provider measures its own app and must not read the reference's expected
counts, geometry, styles or strings to choose a disposition.

## Additive reference correction in this checkpoint

`reference-elements.js` adds `supplementalRegionEvidence`. It retains a region
only after independent live DOM and linked CDP AX evidence establish one of:

1. A `nav` element or explicit `role="navigation"`, with an actually measured,
   nonignored AX navigation role and a nonempty measured AX name.
2. An explicit DOM `tabindex` whose actual `tabIndex` is zero, actual AX
   `focusable=true`, and positive client dimensions with actual overflowing
   content on an axis whose computed overflow is `auto` or `scroll`.

These checks run after the existing classifications in `kindOf`; they add
previously unclassified regions without replacing an existing control,
decoration or text owner. Existing visibility/occlusion checks still apply.
The raw record retains `region_projection_evidence`; the emitted element
retains `evidence.region_projection`, including the original AX record and
DOM/scroll witnesses. The normal raw and canonical identities remain intact.

A scroll region is not a measurement of its scrollbar parts. Thumb, track,
button visibility/geometry and related coverage failures remain independent.
This narrow correction does not claim to resolve every possible semantic
region or action omitted by the broader reference projector.

The CI-only pure Node fixtures use the production functions and transcribed
raw values. They cover both actual omitted cases, rejected missing/ignored AX
evidence, insufficient focus/scroll evidence, both scroll axes, and preservation
of existing semantic/painted kinds. No local browser or Node test is run.

## Recorded counterexamples: 5ff6706 group scene

Evidence root:
`S:\Codex\Outputs\Relic-native-visual\parity-5ff6706\elements\`.
All rows below use `en-US-light-1440x900-group`. These are observations of that
commit, not current whole-matrix totals or desired element counts.

| Artifact | Canonical elements | Regions |
| --- | ---: | ---: |
| `reference-macos/*.elements.json` | 220 | 6 |
| `macos/*.elements.json` | 231 | 31 |
| `windows/*.elements.json` | 235 | 4 |

The different region counts are evidence to investigate, never target counts.

* Reference `dom-56`, `#tree`, has `aria-label="Organizations"` and actual AX
  `role=navigation`, `name=Organizations`, `ignored=false`. Nevertheless its
  projection reason was `layout-only-wrapper-or-owned-label` and its emitted
  list was empty. This is positive semantic evidence for the additive fix.
* Reference `dom-171`, `#stream`, has `tabindex="0"` and actual AX
  `focusable=true`. Its recorded vertical scroll metrics are
  `scrollHeight=969`, `clientHeight=698`. It too was raw-only. These independent
  witnesses establish an interactive scroll viewport; they do not measure a
  scrollbar thumb.
* Mac `window/0` and `window/0/0` are AXGroup nodes at the same `1440x40`
  header rectangle. Their background measurements are null and they have no
  surface evidence. `surface-paint/197` separately records real header fill
  and border. This suggests an ownership problem, but the null fields do not
  prove the AX groups are transparent or noninteractive. Current AX capture
  does not retain sufficient action/focusability evidence to certify absence.
* Mac's 31 regions include 18 AX records and 13 actual surface records. The
  latter are not empty layout objects: `surface-paint/176`, `/191` and `/198`
  have transparent fills but measured border width 1. Their paint must remain;
  any necessary region-to-card classification correction must retain the
  element and its full evidence.
* Mac `window/2/0` and `window/2/1` share identifier
  `relic-region/conversation`, but their heights are respectively 56 and 698.
  These mark the conversation header and stream's region membership, not a
  unique interchangeable semantic owner.
* Windows raw `xaml-53` is a CommandBar named `Window bar`, with a nontransparent
  recorded background, yet its projection reason says it has no own text,
  role, background or border. Its template may own the actual background
  drawing; that requires a measured ownership relation. The generic reason
  does not establish that relation and must not become the common contract.

## Client work still required

The Mac client must distinguish semantic-region ownership from membership,
retain actual action/focusability evidence, and resolve paint ownership for
candidate grouping nodes before changing their disposition. Keep current
uninstrumented-paint and ambiguous-surface failures. The Windows client must
apply the same evidence requirements beyond its type map and accurately
describe template/control paint ownership; retain unmatched UIA failures.
The reference client must preserve the additive cases above and audit any
future generic-wrapper claims using the same proof requirements.

CI should exercise negative cases as well as known layout-only nodes: an
empty-named action target, a transparent bordered/shadowed surface, a focusable
scrollport, a named navigation region, a same-box duplicate with ambiguous
ownership, unknown custom drawing, and a raw-only parent containing visible
children. No exception, scene exclusion, tolerance relaxation, reference-count
target, or unknown-to-zero conversion is permitted by this contract.
