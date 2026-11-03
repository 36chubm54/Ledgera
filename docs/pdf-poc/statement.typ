#set page(
  paper: "a4",
  flipped: true,
  margin: (x: 12mm, y: 11mm),
  numbering: "1 / 1",
)
#set text(font: "Arial", size: 8.5pt, fill: rgb("1D1B20"))
#let data = json("data.json")

#let primary = rgb("6750A4")
#let primary-container = rgb("EADDFF")
#let on-primary-container = rgb("21005D")
#let surface = rgb("F7F2FA")
#let surface-variant = rgb("ECE6F0")
#let outline = rgb("CAC4D0")
#let on-variant = rgb("49454F")
#let income = rgb("1B6D3A")
#let income-container = rgb("C8EBD0")
#let error = rgb("B3261E")
#let error-container = rgb("F9DEDC")
#let transfer = rgb("6750A4")
#let transfer-container = rgb("E8DEF8")

#let pill(label, fill: surface-variant, foreground: on-variant) = box(
  fill: fill,
  radius: 5pt,
  inset: (x: 5pt, y: 2.5pt),
)[#text(size: 7.2pt, weight: "medium", fill: foreground)[#label]]

#let card(body, fill: surface, width: 1fr) = box(
  width: width,
  fill: fill,
  stroke: 0.5pt + outline,
  radius: 7pt,
  inset: 8pt,
)[#body]

#let kpi(label, value, note: none, fill: surface) = card([
  #text(size: 7.5pt, weight: "medium", fill: on-variant)[#label]
  #v(2pt)
  #text(size: 13pt, weight: "medium")[#value]
  #if note != none {
    v(2pt)
    text(size: 7.2pt, fill: on-variant)[#note]
  }
], fill: fill)

#let progress(done, total, label) = {
  let ratio = calc.min(done / total, 1)
  let track = 54pt
  let filled = track * ratio
  grid(
    columns: (auto, 1fr),
    gutter: 5pt,
    align: (left, horizon),
    box(
      width: track,
      height: 6pt,
      fill: surface-variant,
      radius: 3pt,
      clip: true,
    )[
      #box(width: filled, height: 6pt, fill: primary, radius: 3pt)
    ],
    text(size: 7.2pt, fill: on-variant)[#label],
  )
}

#let money(value, color: black) = text(weight: "medium", fill: color)[#value]

#block(
  fill: primary-container,
  radius: 7pt,
  inset: (x: 12pt, y: 8pt),
)[
  #grid(
    columns: (1fr, auto),
    align: (left, right),
    [
      #text(size: 18pt, fill: on-primary-container)[#data.title]
      #linebreak()
      #text(size: 9pt, weight: "medium", fill: on-primary-container)[#data.period]
    ],
    [
      #pill([#data.base_currency ₸], fill: white, foreground: on-primary-container)
      #h(4pt)
      #pill([Operation-time rates], fill: white, foreground: on-primary-container)
      #linebreak()
      #text(size: 7.2pt, fill: on-primary-container)[Ledgera · generated 01.11.2026 12:34]
    ],
  )
]

#v(8pt)
#grid(
  columns: (1fr, 1fr, 1fr, 1fr),
  gutter: 8pt,
  kpi([Opening balance], [+673 939.13 KZT], note: [as of 01.10.2026]),
  kpi([Income], [#money([+103 686.82 KZT], color: income)], note: [all income]),
  kpi([Expenses], [#money([−98 706.00 KZT], color: error)], note: [all expenses]),
  kpi([Net worth], [+678 919.95 KZT], note: [#data.mode mode], fill: primary-container),
)

#v(8pt)
#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: 8pt,
  card([
    #text(weight: "medium", size: 10pt)[By month]
    #v(4pt)
    #table(
      columns: (1.3fr, 1fr, 1fr, 1fr),
      inset: 3pt,
      align: (left, right, right, right),
      table.header([Month], [Income], [Expenses], [Net]),
      [Oct 2026], [#money([+87 418.18 KZT], color: income)], [−97 663.00 KZT], [−10 244.82 KZT],
      [Nov 2026], [#money([+16 268.64 KZT], color: income)], [−1 043.00 KZT], [+15 225.64 KZT],
    )
  ]),
  card([
    #text(weight: "medium", size: 10pt)[Tags]
    #v(4pt)
    #table(
      columns: (1fr, auto, auto),
      inset: 3pt,
      align: (left, right, right),
      [#pill([\#курсач], fill: transfer-container, foreground: transfer)], [4], [−2 500.00 KZT],
      [#pill([\#диплом], fill: transfer-container, foreground: transfer)], [3], [−2 890.00 KZT],
      [#pill([\#батарейки], fill: transfer-container, foreground: transfer)], [2], [−134.00 KZT],
    )
    #v(3pt)
    #text(size: 7pt, fill: on-variant)[Multi-tag operations are counted in each tag.]
  ]),
  card([
    #text(weight: "medium", size: 10pt)[Debts]
    #v(5pt)
    #for debt in data.debts [
      #text(size: 8pt)[#debt.contact · #debt.kind · #debt.status]
      #v(3pt)
      #let paid-label = str(debt.percent) + "% paid"
      #progress(debt.settled, debt.total, [#paid-label])
      #v(4pt)
    ]
    #v(5pt)
    #pill([Reconciles], fill: income-container, foreground: income)
  ]),
)

#pagebreak()
#text(size: 11pt, weight: "medium")[Operations]
#v(4pt)
#table(
  columns: (1.1fr, 1.1fr, 2fr, 2.2fr, 1.4fr),
  inset: 4pt,
  stroke: (x, y) => if y == 0 { none } else { 0.35pt + outline },
  align: (left, left, left, left, right),
  table.header([Date], [Type], [Category], [Tags / description], [Amount]),
  [01.11.2026], [#pill([Income], fill: income-container, foreground: income)], [Cashback], [#pill([\#bonus], fill: transfer-container, foreground: transfer)], [#money([+2 787.06 KZT], color: income)],
  [01.11.2026], [#pill([Expense], fill: error-container, foreground: error)], [Food and drinks], [Lunch], [#money([−94.00 KZT], color: error)],
  [31.10.2026], [#pill([Expense], fill: error-container, foreground: error)], [Stationery], [Office supplies], [#money([−290.00 KZT], color: error)],
  [29.10.2026], [#pill([Transfer], fill: transfer-container, foreground: transfer)], [Transfers], [Deposit BCC], [#money([−210.00 KZT], color: transfer)],
)

#v(8pt)
#text(size: 11pt, weight: "medium")[Transfers]
#v(4pt)
#table(
  columns: (0.6fr, 1fr, 2fr, 2fr, 1.4fr, 1fr, 1.1fr),
  inset: 4pt,
  stroke: (x, y) => if y == 0 { none } else { 0.35pt + outline },
  align: (left, left, left, left, right, right, left),
  table.header([ID], [Date], [From], [To], [Amount], [Rate], [Status]),
  [#452], [31.10.2026], [Main wallet (BCC)], [Deposit BCC], [#money([72.00 KZT], color: transfer)], [1], [#pill([OK], fill: income-container, foreground: income)],
  [#451], [30.10.2026], [Main wallet (BCC)], [Deposit BCC], [#money([68.00 KZT], color: transfer)], [1], [#pill([OK], fill: income-container, foreground: income)],
)

#v(8pt)
#line(length: 100%, stroke: 0.5pt + outline)
#v(3pt)
#grid(columns: (1fr, auto), [Generated in Ledgera], [Prototype])
