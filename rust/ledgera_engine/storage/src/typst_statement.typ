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
#let tag-color = rgb("00695C")
#let tag-container = rgb("D6F5F0")

#let pill(label, fill: surface-variant, foreground: on-variant) = box(
  fill: fill,
  radius: 5pt,
  inset: (x: 5pt, y: 2.5pt),
)[#text(size: 7.2pt, weight: "medium", fill: foreground)[#label]]

#let card(body, fill: surface, width: 1fr, height: auto) = box(
  width: width,
  height: height,
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
    note
  }
], fill: fill, height: 72pt)

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

#let table-fill(_, y) = if y == 0 {
  primary-container
} else if calc.even(y) {
  surface
} else {
  surface-variant
}

#let table-stroke(_, y) = if y == 0 {
  0.5pt + outline
} else {
  0.35pt + outline
}

#let styled-table(..args) = table(
  inset: (x: 5pt, y: 4pt),
  fill: table-fill,
  stroke: table-stroke,
  ..args,
)

#let operation-detail(tags, note) = {
  if tags.len() > 0 {
    for tag in tags [
      #pill(tag.label, fill: rgb(tag.color), foreground: white)
      #h(2pt)
    ]
  }
  if note != "" {
    if tags.len() > 0 {
      linebreak()
    }
    note
  }
}

#let capital-dynamics(points) = {
  if points.len() == 0 {
    return
  }
  let count = points.len()
  let plot-height = 245pt
  let chart-height = 286pt
  let marker = 2.3pt
  card([
    #grid(
      columns: (1fr, auto),
      align: (left, right),
      text(size: 10pt, weight: "medium")[Capital dynamics],
      text(size: 7.5pt, fill: on-variant)[Monthly closing capital],
    )
    #v(4pt)
    #box(width: 100%, height: chart-height)[
      #place(top + left, dx: 24pt, dy: -2pt,
        text(size: 7pt, fill: on-variant, "Sum (" + data.base_currency + ")"))
      #place(top + left, dx: 24pt, dy: 6pt,
        line(end: (0pt, plot-height), stroke: 0.5pt + outline))
      #place(top + left, dx: 24pt, dy: plot-height + 6pt,
        line(end: (696pt, 0pt), stroke: 0.5pt + outline))
      #for tick in data.capital_axis_ticks [
        #let y = (1 - tick.position) * plot-height + 6pt
        #place(top + left, dx: -20pt, dy: y - 4pt,
          box(width: 42pt)[
            #align(right)[#text(size: 6.5pt, fill: on-variant)[#tick.label]]
          ])
      ]
      #for index in range(count - 1) [
        #let first = points.at(index)
        #let second = points.at(index + 1)
        #let first-x = first.x * 1pt
        #let second-x = second.x * 1pt
        #let first-y = (1 - first.position) * plot-height + 6pt
        #let second-y = (1 - second.position) * plot-height + 6pt
        #place(top + left, dx: first-x, dy: first-y,
          line(end: (second-x - first-x, second-y - first-y), stroke: 1.7pt + primary))
      ]
      #for (index, point) in points.enumerate() [
        #let x = point.x * 1pt
        #let y = (1 - point.position) * plot-height + 6pt
        #place(top + left, dx: x - marker, dy: y - marker, circle(radius: marker, fill: primary))
      ]
    ]
    #box(width: 720pt, height: 16pt)[
      #for point in points [
        #place(top + left, dx: point.x * 1pt - 24pt, dy: 0pt,
          box(width: 48pt)[
            #align(center)[#text(size: 6.5pt, fill: on-variant, point.month)]
          ])
      ]
    ]
    #align(right)[#text(size: 7pt, fill: on-variant)[MM-YYYY]]
  ])
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
      #align(right)[
        #pill([#data.base_currency], fill: white, foreground: on-primary-container)
        #h(4pt)
        #pill([#data.mode], fill: white, foreground: on-primary-container)
        #linebreak()
        #text(size: 6.5pt, fill: on-primary-container)[Ledgera · generated #data.generated_at]
      ]
    ],
  )
]

#v(8pt)
#let balance-fill = if data.kpis.balance_delta_positive { income-container } else { error-container }
#let balance-color = if data.kpis.balance_delta_positive { income } else { error }
#let balance-symbol = if data.kpis.balance_delta_positive { "▲" } else { "▼" }
#grid(
  columns: (1fr, 1fr, 1fr, 1fr),
  gutter: 8pt,
  kpi([Opening balance], [#data.kpis.opening_balance]),
  kpi([Income], [#money(data.kpis.income, color: income)], note: [all income]),
  kpi([Expenses], [#money(data.kpis.expenses, color: error)], note: [all expenses]),
  kpi(
    [Final balance],
    [#money(data.kpis.final_balance, color: balance-color)],
    note: [
      #box(fill: balance-fill, radius: 4pt, inset: (x: 4pt, y: 2pt))[
        #text(size: 7.2pt, weight: "medium", fill: balance-color)[#balance-symbol #data.kpis.balance_delta]
      ]
    ],
    fill: balance-fill,
  ),
)

#v(8pt)
#capital-dynamics(data.capital_dynamics)

#v(8pt)
#grid(
  columns: (1.4fr, 1fr),
  gutter: 8pt,
  card([
    #text(weight: "medium", size: 10pt)[By month]
    #v(4pt)
    #let cells = data.monthly.map(row => (
      [#row.month], [#money(row.income, color: income)], [#money(row.expenses, color: error)], [#row.net],
    )).flatten()
    #styled-table(columns: (1.3fr, 1fr, 1fr, 1fr), align: (left, right, right, right),
      table.header([Month], [Income], [Expenses], [Net]), ..cells)
  ]),
  card([
    #text(weight: "medium", size: 10pt)[Tags]
    #v(4pt)
    #let cells = data.tags.map(row => (
      [#pill(row.tag, fill: transfer-container, foreground: transfer)], [#row.operations_count], [#row.amount],
    )).flatten()
    #styled-table(columns: (1fr, auto, auto), align: (left, right, right),
      table.header([Tag], [Operations], [Amount]), ..cells)
  ]),
)

#v(8pt)
#text(weight: "medium", size: 10pt)[Debts]
#v(4pt)
#let debt-cells = data.debts.map(debt => (
  [#debt.contact], [#debt.kind], [#debt.status], [#debt.currency],
  [#debt.total], [#debt.remaining], [#progress(debt.progress_percent / 100, 1, [#debt.progress_label])],
)).flatten()
#styled-table(
  columns: (2fr, 1fr, 1fr, 0.8fr, 1.2fr, 1.2fr, 1.5fr),
  align: (left, left, left, left, right, right, left),
  table.header([Contact], [Kind], [Status], [Currency], [Total], [Remaining], [Progress]),
  ..debt-cells,
)

#pagebreak()
#if data.grouped {
  text(size: 11pt, weight: "medium")[Categories]
  v(4pt)
  let category-cells = data.categories.map(row => (
    [#row.category], [#row.operations_count], [#money(row.amount, color: transfer)],
  )).flatten()
  styled-table(
    columns: (2fr, 1fr, 1.4fr),
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
    [#operation-detail(row.tags, row.note)],
    [#money(row.amount, color: kind-color(row.kind))],
  )).flatten()
  styled-table(
    columns: (1.1fr, 1.1fr, 2fr, 2.2fr, 1.4fr),
    align: (left, left, left, left, right),
    table.header([Date], [Type], [Category], [Tags / note], [Amount]),
    ..operation-cells,
  )
}

#v(8pt)
#text(size: 11pt, weight: "medium")[Transfers]
#v(4pt)
#let transfer-cells = data.transfers.map(row => (
  [#row.transfer_id], [#row.date], [#row.from_wallet], [#money(row.source_amount, color: transfer)],
  [#row.to_wallet], [#money(row.target_amount, color: transfer)],
  [#row.historical_rate], [#row.commission], [#pill(row.status, fill: income-container, foreground: income)], [#row.note],
)).flatten()
#styled-table(
  columns: (0.6fr, 0.9fr, 2fr, 1.35fr, 2fr, 1.35fr, 0.9fr, 1.1fr, 0.9fr, 1.5fr),
  align: (left, left, left, right, left, right, right, left, left, left),
  table.header([ID], [Date], [From], [Sent], [To], [Received], [Rate], [Commission], [Status], [Note]),
  ..transfer-cells,
)

#v(8pt)
#line(length: 100%, stroke: 0.5pt + outline)
#v(3pt)
#grid(columns: (1fr, auto), [Generated in Ledgera], [#data.mode])
