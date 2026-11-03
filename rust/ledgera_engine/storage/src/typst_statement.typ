#set page(
  paper: "a4",
  flipped: true,
  margin: (x: 12mm, y: 11mm),
  numbering: "1 / 1",
)
#set text(font: "__LEDGER_FONT_FAMILY__", size: 8.5pt, fill: rgb("1D1B20"))
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
    box(width: track, height: 6pt, fill: surface-variant, radius: 3pt, clip: true)[
      #box(width: filled, height: 6pt, fill: primary, radius: 3pt)
    ],
    text(size: 7.2pt, fill: on-variant)[#label],
  )
}

#let money(value, color: black) = text(weight: "medium", fill: color)[#value]
#let kind-fill(kind) = if kind == "income" { income-container } else if kind == "expense" { error-container } else { transfer-container }
#let kind-color(kind) = if kind == "income" { income } else if kind == "expense" { error } else { transfer }

#block(fill: primary-container, radius: 7pt, inset: (x: 12pt, y: 8pt))[
  #grid(
    columns: (1fr, auto),
    align: (left, right),
    [
      #text(size: 18pt, fill: on-primary-container)[#data.title]
      #linebreak()
      #text(size: 9pt, weight: "medium", fill: on-primary-container)[#data.period]
    ],
    [
      #pill([#data.base_currency], fill: white, foreground: on-primary-container)
      #h(4pt)
      #pill([#data.mode], fill: white, foreground: on-primary-container)
    ],
  )
]

#v(8pt)
#grid(
  columns: (1fr, 1fr, 1fr, 1fr),
  gutter: 8pt,
  kpi([Opening balance], [#data.kpis.opening_balance]),
  kpi([Income], [#money(data.kpis.income, color: income)], note: [all income]),
  kpi([Expenses], [#money(data.kpis.expenses, color: error)], note: [all expenses]),
  kpi([Final balance], [#data.kpis.final_balance], note: [#data.mode mode], fill: primary-container),
)

#v(8pt)
#grid(
  columns: (1.1fr, 1fr, 1fr),
  gutter: 8pt,
  card([
    #text(weight: "medium", size: 10pt)[By month]
    #v(4pt)
    #let cells = data.monthly.map(row => (
      [#row.month], [#money(row.income, color: income)], [#money(row.expenses, color: error)], [#row.net],
    )).flatten()
    #table(columns: (1.3fr, 1fr, 1fr, 1fr), inset: 3pt, align: (left, right, right, right),
      table.header([Month], [Income], [Expenses], [Net]), ..cells)
  ]),
  card([
    #text(weight: "medium", size: 10pt)[Tags]
    #v(4pt)
    #let cells = data.tags.map(row => (
      [#pill(row.tag, fill: transfer-container, foreground: transfer)], [#row.operations_count], [#row.amount],
    )).flatten()
    #table(columns: (1fr, auto, auto), inset: 3pt, align: (left, right, right), ..cells)
  ]),
  card([
    #text(weight: "medium", size: 10pt)[Debts]
    #v(5pt)
    #for debt in data.debts [
      #text(size: 8pt)[#debt.contact · #debt.kind · #debt.status]
      #v(3pt)
      #progress(debt.progress_percent / 100, 1, [#debt.progress_label])
      #v(4pt)
    ]
  ]),
)

#pagebreak()
#if data.grouped {
  text(size: 11pt, weight: "medium")[Categories]
  v(4pt)
  let category-cells = data.categories.map(row => (
    [#row.category], [#row.operations_count], [#money(row.amount, color: transfer)],
  )).flatten()
  table(
    columns: (2fr, 1fr, 1.4fr),
    inset: 4pt,
    stroke: (x, y) => if y == 0 { none } else { 0.35pt + outline },
    align: (left, right, right),
    table.header([Category], [Operations], [Amount]),
    ..category-cells,
  )
} else {
  text(size: 11pt, weight: "medium")[Operations]
  v(4pt)
  let operation-cells = data.operations.map(row => (
    [#row.date],
    [#pill(row.type_label, fill: kind-fill(row.kind), foreground: kind-color(row.kind))],
    [#row.category],
    [#row.tags #if row.description != "" [#linebreak() #row.description]],
    [#money(row.amount, color: kind-color(row.kind))],
  )).flatten()
  table(
    columns: (1.1fr, 1.1fr, 2fr, 2.2fr, 1.4fr),
    inset: 4pt,
    stroke: (x, y) => if y == 0 { none } else { 0.35pt + outline },
    align: (left, left, left, left, right),
    table.header([Date], [Type], [Category], [Tags / description], [Amount]),
    ..operation-cells,
  )
}

#v(8pt)
#text(size: 11pt, weight: "medium")[Transfers]
#v(4pt)
#let transfer-cells = data.transfers.map(row => (
  [#row.transfer_id], [#row.date], [#row.from_wallet], [#row.to_wallet],
  [
    #text(size: 7pt, weight: "medium", fill: on-variant)[Source]
    #h(2pt)
    #money(row.source_amount, color: transfer)
    #linebreak()
    #text(size: 7pt, weight: "medium", fill: on-variant)[Target]
    #h(2pt)
    #money(row.target_amount, color: transfer)
    #linebreak()
    #text(size: 7pt, weight: "medium", fill: on-variant)[Base]
    #h(2pt)
    [#row.source_base_amount / #row.target_base_amount]
  ],
  [#row.historical_rate], [#row.commission], [#pill(row.status, fill: income-container, foreground: income)],
)).flatten()
#table(
  columns: (0.6fr, 1fr, 2fr, 2fr, 1.8fr, 1fr, 1.3fr, 1.1fr),
  inset: 4pt,
  stroke: (x, y) => if y == 0 { none } else { 0.35pt + outline },
  align: (left, left, left, left, right, right, left),
  table.header([ID], [Date], [From], [To], [Source / Target], [Rate], [Commission], [Status]),
  ..transfer-cells,
)

#v(8pt)
#line(length: 100%, stroke: 0.5pt + outline)
#v(3pt)
#grid(columns: (1fr, auto), [Generated in Ledgera], [#data.mode])
