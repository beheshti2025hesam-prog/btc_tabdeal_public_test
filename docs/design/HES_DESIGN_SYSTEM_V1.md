# HES Trade Agent — Design System v1

**Project:** HES Trade Agent  
**Owner:** Seyed Hesameddin Beheshti Shirazi  
**Status:** Design foundation / prototype specification  
**Principle:** Minimal · Artistic · Distinctive · Timeless

## 1. Design DNA

HES is designed as a **timeless-futurist command center**, not a trend-driven dashboard.

The visual language must remain credible and contemporary across a long product lifetime. Avoid visual dependencies on short-lived styles such as excessive neon, cyberpunk decoration, heavy glassmorphism, ornamental gradients, or dense card grids.

### Core principles

1. **Minimal** — every visible element must have a reason to exist.
2. **Artistic** — identity comes from composition, mineral-inspired color, typography, geometry, and restrained light.
3. **Distinctive** — HES must be recognizable without relying on generic trading-dashboard conventions.
4. **Timeless** — structure and semantic tokens must outlive individual visual trends.
5. **Evidence-first** — visual polish must never hide provenance, uncertainty, risk, or limitations.
6. **Progressive disclosure** — show the minimum useful information first; reveal depth on demand.

## 2. Visual Language

### Mineral-inspired semantic palette

The initial palette family is intentionally semantic rather than hard-coded:

- **Obsidian** — primary background / depth / focus
- **Amethyst** — intelligence / discovery
- **Lapis** — market / data
- **Malachite** — valid / healthy / passed
- **Copper** — attention / opportunity / review
- **Platinum** — neutral information / structure
- **Pearl** — high-contrast text in dark mode

Exact HEX values remain a prototype decision until tested against real screens, chart density, accessibility, and all supported languages.

### Color rule

Color is not decoration. Every color must have a semantic role.

Status must never depend on color alone. Use text, iconography, shape, or pattern as a second channel.

## 3. Typography

The typography system must support:

- Latin
- Persian / RTL
- Chinese
- Japanese
- multilingual fallback
- financial/data numerals
- Dynamic text sizing

Candidate Latin families: **Inter, IBM Plex Sans, Geist**.  
Candidate Persian family: **Vazirmatn**.

Final selection is an evidence-based prototype decision, not a hard-coded assumption.

Numerical displays should support tabular numerals so aligned values remain visually comparable.

## 4. Themes

Two official themes:

- **HES Dark** — primary command-center environment
- **HES Light** — alternative long-session / bright-environment mode

Both themes must share the same semantic token names.

Theme changes must not require application restart.

## 5. Information Architecture

Primary user flow:

**Pulse → Context → Evidence → Decision**

### Core areas

1. Command Center
2. Market
3. Intelligence
4. Risk
5. Decision
6. Evidence
7. Data Integrity
8. OOS / Backtest
9. Agent / Mother Agent
10. Settings

### One-page / one-question rule

Each primary screen should answer one dominant question.

- **Command Center:** What is the current system state?
- **Market:** What is the market state?
- **Intelligence:** Why did this signal/state form?
- **Risk:** What can veto or constrain the decision?
- **Decision:** What is the current decision state?
- **Evidence:** What evidence supports that state?

## 6. Decision States

First-class states:

- **READY**
- **LIVE**
- **REVIEW**
- **VETO**
- **NO TRADE**
- **OFFLINE**

**NO TRADE is a valid decision, not an error state.**

Example:

> NO TRADE — Confirmation threshold not reached.

## 7. Evidence Model

The visual system must support an auditable chain:

**Raw Data → Feature → Signal → Risk/Veto → Decision → Outcome**

Evidence views should expose, where available:

- snapshot/provenance identifier
- timestamps
- sequence integrity
- feature boundaries
- OOS evidence
- cost/slippage boundary
- risk state
- execution state
- audit trail

Performance numbers must not be presented without context such as sample size, time period, OOS status, costs, and limitations.

## 8. Core Components

### Navigation
- Command Bar
- Desktop Sidebar
- Mobile Navigation
- Breadcrumb

### Status
- System Status
- Data Status
- Risk Status
- Decision Status

### Data
- Metric
- Data Card
- Table
- Timeline

### Intelligence
- Signal Card
- Evidence Card
- Confidence Indicator
- Decision Panel

### Visualization
- Market Chart
- Performance Chart
- OOS Chart
- Risk Chart

### Interaction
- Button
- Toggle
- Select
- Slider
- Command Input

### Feedback
- Alert
- Warning
- Veto
- Success
- Audit Message

## 9. Signature Component

### DecisionEvidence

A signature HES component that connects a decision to its evidence.

Conceptual structure:

    DECISION
    NO TRADE

    Structure       PASS
    Opportunity     PASS
    Confirmation    WAIT
    Risk            PASS
    Execution       OFF

    Evidence
      Raw Data Integrity
      Timestamp Integrity
      Sequence Integrity
      Feature Boundary
      OOS Evidence
      Cost Boundary

    [VIEW DETAILS] [AUDIT TRAIL]

## 10. HES Pulse

A restrained visual indicator for overall system state.

It should use subtle geometry/light rather than a decorative animated logo.

Motion must communicate state transitions and never become a distraction.

## 11. Motion Language

Motion is:

- short
- calm
- predictable
- purposeful
- interruptible where appropriate
- disabled/reduced under accessibility preferences

No decorative animation should be required to understand system state.

## 12. Localization

Initial supported languages:

1. English
2. فارسی
3. Deutsch
4. Français
5. Español
6. 中文
7. 日本語

Requirements:

- runtime language switching
- no restart required
- full Unicode
- RTL/LTR support
- localized date/time formatting
- localized number formatting
- layout resilience for text expansion
- CJK typography fallback
- accessibility-aware text scaling

The architecture must permit additional languages without changing HES Core.

## 13. Responsive Platform Strategy

One HES Core and one semantic design system; platform-specific interaction layers.

### Windows

Target artifact: **.exe**

Optimized for desktop command-center layouts, large displays, keyboard/mouse, and multi-panel workflows.

### Android

Target artifact: **.apk**

Mobile-first interaction, touch targets, focus-first information hierarchy.

### Apple

Target artifact: **.ipa**

iPhone/iPad adaptive layouts, touch-first interaction, safe-area handling, dynamic type, portrait/landscape support.

### Future macOS

Target artifact: **.app**

Can reuse HES Core and design-system contracts.

**Shared Core does not mean identical UI.** Each platform should preserve the HES information model while respecting platform interaction conventions.

## 14. Architecture Boundary

The UI must not directly execute exchange actions.

Conceptual boundary:

**UI → Command Layer → Safety Gates → Execution Layer**

Current project policy remains:

**Live execution OFF.**

The Design System must remain independent from trading/data-engine implementation details.

## 15. Design Tokens

Components must consume semantic tokens rather than hard-coded visual values.

Conceptual model:

**Token → Semantic Meaning → Component → State**

This allows future visual evolution without rewriting HES Core.

## 16. Accessibility

The foundation includes:

- color-independent status communication
- contrast validation
- keyboard navigation
- scalable text
- reduced-motion mode
- touch-safe controls
- readable data tables
- screen-reader-compatible semantic structure where platform permits

## 17. Prototype Acceptance Gate

Before final visual tokens are frozen, prototype validation must cover:

- Command Center
- DecisionEvidence
- one market visualization
- Dark + Light
- English + Persian + German
- at least one CJK language
- desktop
- Android-sized mobile
- iPhone/iPad-sized layouts
- long text / RTL expansion
- accessibility contrast
- data-heavy tables and charts

Only after these checks should exact HEX values, font weights, spacing scale, and pixel-level component dimensions be considered frozen.

## 18. Product Output Roadmap

**HES Core → Design System → Command Center → Evidence → Settings → Platform adaptation**

Target release families:

- Windows **.exe**
- Android **.apk**
- Apple iPhone/iPad **.ipa**
- Future macOS **.app**

This document defines the design foundation only. It does not authorize live execution, raw-data mutation, changes to `data-engine-v1`, or changes to the collector safety gates.
