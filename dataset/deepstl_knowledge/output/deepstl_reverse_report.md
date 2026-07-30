# DeepSTL Knowledge Reverse Report

## Scope

- Source: `deepstl_train_14k.csv` + `deepstl_test_2k.csv`
- Processed range: train rows 1–14318; test rows 1–2000
- Current batch: test rows 1501–2000
- Batch state: the current batch is complete
- Knowledge-base update: performed after test row 2000 for the current batch

## Method

Each source row was requested separately through
`deepstl_knowledge/scripts/read_deepstl_row.py`.

The reader returned only the raw row index, split, STL, English, and Type.
It did not parse STL, segment English, replace placeholders, classify
structures, extract patterns, deduplicate knowledge, or write the knowledge
base.

For every row, the LLM directly:

1. interpreted the STL and English pair;
2. separated the formula, temporal subexpressions, predicates, modifiers, and
   Boolean compositions;
3. aligned the observed English wording with those semantic roles;
4. produced reusable patterns;
5. checked comparison direction, negation, event direction, and time scope.

After the last row of the current batch, the LLM merged its extracted
knowledge into the maintained TXT knowledge base and this report.

## Output policy

- Temporal operators use `always`, `eventually`, `historically`, `once`,
  `until`, and `since`.
- Nested structures use forms such as `always(eventually(...))` and
  `eventually(always(...))`.
- Empty NL fields are omitted.
- The knowledge base contains only reusable semantic and wording patterns.
- Deduplication was semantic and performed by the LLM within the same template
  and context.

## Review notes

- The observed `not fall(eventually(...))` wording is restricted to a temporal
  input and is not generalized to ordinary predicates.
- The second batch also contains `rise(always(...))` and
  `fall(until(...))`; their event wording remains restricted to temporal
  inputs.
- The observed wording for `not(always(...))` is retained with an explicit
  restriction because the scope of negation must not be moved during reuse.
- Patterns involving `rise` and `fall` remain event expressions; they are not
  rewritten as persistent states.
- The third batch adds a left-open right-closed interval predicate
  `<LOW> < <SIGNAL> <= <HIGH>`.
- The third batch expands `until` so event absence can appear on the left and
  an event can appear on the right, matching rows with `not fall(...) until`
  and `until ... rise(...)`.
- The third batch adds temporal-input `not rise(<TEMPORAL_RESPONSE>)` and
  event versions of unbounded `always(eventually(...))`.
- The fourth batch adds whole-expression temporal negation such as
  `not(eventually[...](...))` and `not(<TEMPORAL_RESPONSE>)`; negation scope
  is retained over the complete temporal expression.
- The fourth batch adds bounded-past event-happened semantics via
  `once[...](<EVENT_REQUIREMENT>)` and unbounded-past event absence via
  `historically(<EVENT_REQUIREMENT>)`.
- The fourth batch expands nested stabilization and recurrence wording for
  nonzero outer and inner time bounds.
- The fifth batch adds unbounded `since`, state/event variants of bounded
  temporal negation, and temporal-input `rise`, `not rise`, and `fall`
  expressions over past or binary temporal subexpressions.
- The fifth batch adds nested stabilization where the inner sustained
  requirement is event absence, such as `eventually(always(not rise(...)))`.
- JSON output is no longer maintained after row 200 by user instruction; the
  canonical maintained knowledge files are TXT and this report.
- The sixth batch adds unbounded outer `eventually(always[...](...))`,
  bounded outer `always(eventually(...))` with unbounded inner event response,
  past-to-past `once[...](...)` responses, and temporal-input
  `fall/not_fall/rise/not_rise` triggers.
- The sixth batch also adds state and event variants of whole-expression
  `not(always[...](...))` and `not(until[...](...))` without moving negation
  inside the temporal expression.
- The seventh batch adds unbounded `once(<EVENT_REQUIREMENT>)`, unbounded
  `since` with event right-hand sides, event-absence reachability inside
  recurrence templates, and unbounded `not(always(...))` temporal negation.
- The seventh batch also expands mixed `always[...](event_absence or state)`
  requirements and left-open-right-closed intervals in temporal responses.
- The eighth batch adds unbounded `not(eventually(...))`, bounded
  `not(since[...](...))`, and `eventually[...](always(event_absence))`
  stabilization patterns.
- The eighth batch expands bounded recurrence templates with nonzero outer and
  inner windows, including event and event-absence inner requirements.
- The ninth batch adds whole-expression `not(always(...))` and
  `not(always[...](...))`, bounded `not(until[...](...))` with
  event-absence terminators, and mixed event-absence/state reachability and
  invariance requirements.
- The ninth batch adds bounded `once[...]` responses and bounded
  `historically[...]` responses.
- The tenth batch adds bounded eventual stabilization into unbounded
  `always(...)`, unbounded `since` triggers, and temporal triggers built from
  bounded `eventually[...]`, `once[...]`, and `historically[...]`.
- The tenth batch expands bounded `since[...]` so the right side can be an
  event-absence expression, and adds response patterns where `fall(...)` or
  `rise(...)` apply to complete temporal subexpressions.
- The eleventh batch adds bounded `since[...]` as a response, temporal
  modifiers over complete temporal subexpressions, and bounded outer
  recurrence with unbounded event reachability.
- The eleventh batch expands bounded invariance and immediate-response cases
  where event-absence and state/range requirements are combined with `or` or
  `and`.
- The twelfth batch adds temporal triggers such as
  `not rise(once[...](rise(...)))`, `rise(once(...))`, and
  `not(historically[...](...))`.
- The twelfth batch expands bounded and unbounded `until`/`since` responses,
  plus recurrence patterns whose inner reachability target is an event or
  event-absence requirement.
- The thirteenth batch adds bounded `until[...]` triggers paired with bounded
  `since[...]` responses, and whole-expression negation over `until[...]`
  where the left side is event absence.
- The thirteenth batch expands recurrence where the stabilized inner
  requirement is event absence, and temporal responses where `rise(...)`
  applies to a complete bounded `eventually[...]` subexpression.
- The fourteenth batch adds temporal triggers formed from unbounded
  `always(...)`, bounded `always[...]`, and unbounded `eventually(...)`.
- The fourteenth batch expands bounded `not(always[...](...))`, bounded
  `historically[...]` responses, and temporal-response cases where
  `rise(...)` applies to a complete bounded `always[...]` expression.
- The fifteenth batch adds `fall(...)` over complete `since(...)`
  expressions, `not rise(...)` over complete bounded `until[...]`
  expressions, and whole-expression negation over bounded `until[...]`.
- The fifteenth batch expands unbounded-eventual stabilization into bounded
  `always[...]`, bounded `since[...]` triggers paired with bounded
  `until[...]` responses, and unbounded `not(eventually(...))` responses.
- The sixteenth batch adds bounded `not(always[...](...))` wording, bounded
  `until[...]` responses with event right-hand sides, and event-absence
  requirements used inside bounded and unbounded `since`.
- The sixteenth batch expands temporal modifiers with `not fall(always(...))`
  and `not rise(until[...](...))`, plus mixed state/event reachability in
  bounded and unbounded `eventually`.
- The seventeenth batch adds temporal triggers such as `fall(once(...))` and
  `not(once[...](...))`, and keeps their negation/modifier scope over the
  whole temporal subexpression.
- The seventeenth batch expands bounded recurrence with large outer/inner
  windows, bounded `since[...]` responses, and bounded `until[...]` responses
  whose right side is an event.
- The eighteenth batch adds temporal modifiers over complete bounded and
  unbounded `always(...)` expressions, plus `not rise(...)` over bounded
  `since[...]` triggers.
- The eighteenth batch expands bounded `not(eventually[...](...))`, unbounded
  `until` with event-absence terminators, and bounded `until[...]` responses
  whose right side may be a negated state or event.
- The nineteenth batch adds history-based triggers with bounded
  `historically[...]`, unbounded `historically(...)`, bounded `once[...]`,
  unbounded `once(...)`, and negated bounded `once[...]`.
- The nineteenth batch expands responses where a complete temporal expression
  is negated, including `not(always[...](...))` and whole unbounded
  `until(...)` expressions; negation scope is preserved over the full temporal
  expression.
- The nineteenth batch adds temporal antecedents that are full bounded
  `until[...]` formulas and responses where bounded `since[...]` or bounded
  `until[...]` has state, event, or range predicates on either side.
- The nineteenth batch expands stabilization/recurrence with
  `eventually[...](always[...](...))`, `eventually[...](always(...))`,
  `always[...](eventually(...))`, and unbounded
  `always(eventually[...](...))` combinations.
- The nineteenth batch adds immediate-response triggers formed by event/state
  conjunctions or disjunctions, plus reachability cases for bounded
  `eventually[...]` over state, event, and mixed requirements.
- The twentieth batch adds more temporal antecedents, including bounded
  `eventually[...]` over states, events, and event-absence requirements, plus
  unbounded `eventually(...)` antecedents.
- The twentieth batch expands past temporal responses where the consequent is
  bounded `historically[...]`, including responses triggered by events or by
  bounded future reachability antecedents.
- The twentieth batch adds whole-expression transitions over temporal
  subexpressions, including `fall(eventually[...](rise(...)))` and
  `rise(until[...](...))`, with modifier scope retained over the full
  temporal subexpression.
- The twentieth batch expands reachability targets that mix events,
  event-absence requirements, and states with `and` or `or`.
- The twentieth batch expands recurrence templates with negated predicates
  inside `always(eventually(...))` and bounded
  `always[...](eventually[...](...))`.
- The twenty-first batch adds bounded `historically[...]` triggers over
  event-absence requirements and bounded `historically[...]` responses over
  state or mode predicates.
- The twenty-first batch expands bounded `since[...]` responses whose right
  side may be a rise event or an event-absence requirement, and whose left
  side may be a negated predicate.
- The twenty-first batch adds whole-expression temporal modifiers such as
  `fall(since[...](...))`, `rise(since[...](...))`,
  `rise(eventually(...))`, and whole negation over bounded or unbounded
  `until(...)` expressions.
- The twenty-first batch expands mixed reachability/invariance targets that
  combine state, event, event-absence, and negated-state requirements with
  `and` or `or`.
- The twenty-first batch adds stabilization patterns for
  `eventually(always(...))` with negated predicates and recurrence patterns
  with large decimal/nonzero time windows.
- The twenty-second batch adds bounded `historically[...]` triggers and
  responses with nonzero past windows, plus bounded `once[...]` and negated
  bounded `once[...]` triggers/responses.
- The twenty-second batch expands `until` and `since` interactions, including
  bounded `since[...]` antecedents followed by unbounded `until(...)`
  responses and whole negation over bounded or unbounded `until(...)`.
- The twenty-second batch adds temporal modifiers over complete unbounded
  temporal subexpressions, including `rise(always(...))`,
  `fall(always(...))`, and `rise(eventually(...))`.
- The twenty-second batch expands event/state mixed reachability targets under
  bounded and unbounded `eventually(...)`, including conjunctions and
  disjunctions of states, events, event absence, and negated ranges.
- The twenty-second batch expands recurrence/stabilization with decimal,
  large, and nonzero outer or inner windows.
- The twenty-third batch adds more bounded invariance wording, including
  “for at least” duration phrasing and small decimal windows.
- The twenty-third batch expands responses driven by bounded or unbounded
  historical conditions, including `once(...)`, `once[...]`, `since[...]`,
  and `not fall(eventually(...))` temporal triggers.
- The current 500-row batch confirms that no new top-level template family is
  needed; the rows combine existing state, mode, range, event, event-absence,
  and temporal atoms under Boolean composition.
- The current 500-row batch expands complete-formula temporal modifiers such
  as `rise(always[...](...))`, `rise(eventually[...](...))`,
  `fall(once[...](...))`, `fall(historically[...](...))`,
  `not rise(eventually(...))`, and `not fall(until[...](...))`.
- The current 500-row batch expands cross-time responses where `since`,
  `since[...]`, `once`, `once[...]`, `historically`, `historically[...]`,
  `until`, and `until[...]` can appear on either side of the implication with
  mixed atom types.
- Rows 5551–6050 keep the same top-level template families and add denser
  combinations of temporal triggers with recurrence and temporal-response
  consequents.
- Rows 5551–6050 add complete-formula modifier cases including
  `not fall(historically[...](...))`, `rise(historically[...](...))`,
  `fall(eventually(...))`, `fall(once[...](...))`,
  `not fall(always[...](...))`, and `not rise(until[...](...))`.
- Rows 5551–6050 expand cross-time response pairings with `since[...]`,
  `since`, `until[...]`, `until`, `once[...]`, `historically[...]`, and
  `historically` used as triggers or consequents for bounded/unbounded
  always/eventually, whole-negated temporal formulas, and recurrence.
- Rows 6051–6550 keep the same top-level template families and mainly add
  denser combinations of past/future temporal formulas with temporal-response
  and recurrence consequents.
- Rows 6051–6550 add complete-formula modifier cases including
  `rise(eventually[...](...))`, `rise(until(...))`,
  `not fall(until[...](...))`, `fall(always(...))`,
  `not fall(always[...](...))`, `rise(once[...](...))`,
  `rise(always[...](...))`, `fall(until[...](...))`,
  `fall(eventually(...))`, `not rise(eventually[...](...))`, and
  `fall(since[...](...))`.
- Rows 6051–6550 expand cross-time pairings where `since`, `since[...]`,
  `once`, `once[...]`, `historically`, `historically[...]`, `until`, and
  `until[...]` connect bounded/unbounded always/eventually responses,
  whole-negated temporal formulas, past responses, and recurrence.
- Rows 6551–7050 remain within the existing template families while adding
  more temporal-formula triggers and responses with long, delayed, and
  decimal windows.
- Rows 6551–7050 add complete-formula modifier cases including
  `not fall(eventually(...))`, `rise(eventually[...](...))`,
  `not fall(once(rise(...)))`, `rise(always(...))`,
  `rise(always[...](...))`, `rise(until(...))`,
  `not rise(until(...))`, `rise(since[...](...))`, `rise(once(...))`,
  `not fall(since(...))`, and `rise(since(...))`.
- Rows 6551–7050 expand cross-time pairings where `historically`,
  `historically[...]`, `once`, `once[...]`, `since`, `since[...]`,
  `until`, `until[...]`, `eventually`, and `eventually[...]` act as
  antecedents or consequents for bounded/unbounded eventually/always,
  bounded once, bounded historically, whole-negated temporal formulas, and
  recurrence.
- Rows 7051–7550 confirm that existing reusable templates cover
  immediate state/event mixtures, event absence, range entry/exit, and mode
  predicates without requiring row-level traces.
- Rows 7051–7550 expand temporal-response coverage around bounded
  `since[...]` antecedents, bounded/unbounded `until` consequents,
  bounded `historically[...]` consequents, whole-negated temporal responses,
  and complete-formula modifiers such as `rise(always(...))`,
  `fall(always(...))`, and `not rise(until(...))`.
- Rows 7051–7550 expand stabilization/recurrence coverage for mixed bounded
  and unbounded nesting, including eventual stabilization, sliding-window
  recurrence, delayed inner windows, and inner event or event-absence targets.
- Rows 7051–7550 add no new top-level template family; the rows
  remain covered by invariance/reachability, immediate response, temporal
  response, and stabilization/recurrence.
- Rows 7051–7550 add more scope-sensitive temporal modifiers over complete
  subformulas, including `not rise(once[...](...))`,
  `not fall(always[...](...))`, `rise(since[...](...))`,
  `fall(since[...](...))`, `not fall(until(...))`,
  `not rise(until[...](...))`, `rise(always[...](...))`,
  `fall(always(...))`, and `not rise(always[...](...))`.
- Rows 7051–7550 expand mixed past/future triggers and responses using
  `since[...]`, unbounded `since`, `once`, `once[...]`, `historically`,
  `historically[...]`, bounded `always[...]`, unbounded `always`,
  bounded `eventually[...]`, and unbounded `eventually` with state, mode,
  range, event, event-absence, and whole-negated atoms.
- Rows 7551–8050 remain within the existing template families and add denser
  use of complete temporal formulas as modified events.
- Rows 7551–8050 expand temporal-response coverage with
  `rise(eventually[...](...))`, `fall(eventually[...](...))`,
  `fall(always[...](...))`, `not fall(eventually[...](...))`,
  `not fall(always[...](...))`, `not rise(always(...))`, bounded
  `historically[...]` consequents, unbounded `historically` consequents, and
  past `once` consequents.
- Rows 7551–8050 expand stabilization/recurrence coverage where antecedents
  are built from `historically[...]`, `since[...]`, `until[...]`,
  `once[...]`, whole-negated future/past formulas, and mixed state/event
  disjunctions.
- Rows 7551–8050 add no new top-level template family; the useful change is
  larger delayed windows, decimal windows, inner event-absence targets, and
  immediate outputs mixing state predicates with not-rise/not-fall atoms.
- The twenty-third batch adds temporal-response cases where a bounded
  `until[...]` antecedent triggers unbounded `not(eventually(...))`, and
  where event triggers require bounded `once[...]` past evidence.
- The twenty-third batch expands unbounded recurrence with large nonzero
  inner event windows, plus bounded recurrence with decimal and nonzero
  inner or outer windows.
- The twenty-third batch adds additional mixed immediate and reachability
  targets formed from conjunctions/disjunctions of states, events, negated
  predicates, and range predicates.
- The twenty-fourth batch expands unbounded and bounded `until` responses,
  including short decimal windows, event-absence left sides, closed/open range
  terminators, and whole-expression modifiers such as
  `rise(until[...](...))` and `not fall(until(...))`.
- The twenty-fourth batch adds event-absence requirements inside bounded
  `once[...]`, bounded `always[...]`, and `eventually(always[...](...))`
  response structures.
- The twenty-fourth batch expands recurrence patterns with large nonzero
  outer windows, nonzero inner windows, and decimal inner deadlines for both
  state and event targets.
- The twenty-fourth batch adds stabilization variants such as unbounded
  `eventually(always[...](...))`, bounded `eventually[...](always(...))`,
  and unbounded `eventually(always(...))`.
- The twenty-fourth batch expands immediate-response and reachability targets
  that combine events, states, event absence, negated predicates, and interval
  predicates with `and` or `or`.
- The twenty-fifth batch adds further negated temporal antecedents, including
  whole negation over bounded `since[...]` and temporal modifiers such as
  `not rise(since(...))` and `not fall(until(...))`.
- The twenty-fifth batch expands bounded and unbounded `once(...)` triggers
  over events, including cases where bounded past events trigger long
  recurrence or bounded always responses.
- The twenty-fifth batch adds bounded `since[...]` antecedents with decimal
  past windows, plus bounded eventually responses over rise events.
- The twenty-fifth batch expands recurrence/stabilization with large and
  decimal windows, including unbounded recurrence with large inner event
  windows and bounded eventually-to-always stabilization.
- The twenty-fifth batch expands immediate and reachability patterns with
  dual event triggers, negated range/state triggers, OR responses, and mixed
  event/state targets.
- The twenty-sixth batch adds temporal triggers such as
  `fall(once(rise(...)))`, `rise(once[...](...))`, and whole negation over
  bounded `eventually[...]` event requirements.
- The twenty-sixth batch expands past-response patterns with unbounded
  `once(rise(...))` and bounded `historically[...]` triggers with nonzero
  past windows.
- The twenty-sixth batch adds `until` responses with event-absence
  terminators and whole-expression negation over unbounded `until(...)`
  formulas whose left side may be event absence.
- The twenty-sixth batch expands recurrence/stabilization with unbounded
  `always(eventually(...))`, bounded outer recurrence with unbounded inner
  eventuality, and large/decimal inner windows.
- The twenty-sixth batch expands immediate, invariance, and reachability
  patterns with negated predicates, event-absence requirements, OR event
  responses, and mixed interval/state targets.
- The twenty-seventh batch adds bounded `since[...]` antecedents feeding
  bounded recurrence responses, and bounded `always[...]` temporal antecedents
  feeding bounded eventual responses.
- The twenty-seventh batch expands `until` responses with large nonzero
  bounded windows, unbounded terminators, negated terminators, and
  event-absence terminators.
- The twenty-seventh batch adds whole-expression temporal negation over
  bounded/unbounded `always(...)` and `until(...)` responses.
- The twenty-seventh batch expands recurrence/stabilization with very large
  decimal windows, unbounded inner eventuality, and nonzero inner windows over
  negated predicates, states, and events.
- The twenty-seventh batch expands immediate and reachability patterns with
  dual-event targets, OR event/state targets, event absence combined with
  state requirements, and mixed interval predicates.
- The twenty-eighth batch adds bounded `since[...]` responses whose right side
  may be a negated state, plus unbounded `since` responses triggered by
  event/state conjunctions.
- The twenty-eighth batch expands historical and event-absence triggers,
  including `historically(not fall(...))` and `rise(always(...))` over full
  temporal subexpressions.
- The twenty-eighth batch expands whole-expression negation over bounded and
  unbounded `always(...)` and `until(...)` responses.
- The twenty-eighth batch adds recurrence/stabilization patterns with decimal
  outer windows, large inner windows, unbounded inner eventuality, and
  nonzero bounded recurrence intervals.
- The twenty-eighth batch expands mixed invariance, reachability, and
  immediate-response targets involving negated states, event absence, OR
  state/event targets, and range predicates.
- The twenty-ninth batch adds further stabilization and recurrence patterns:
  unbounded `eventually(always[...](...))`, bounded
  `eventually[...](always[...](...))`, bounded
  `always[...](eventually[...](...))`, and bounded
  `always[...](eventually(...))` with unbounded inner event eventuality.
- The twenty-ninth batch expands delayed and decimal timing, including
  nonzero bounded `always[...]` responses, nonzero bounded
  `eventually[...]` formulas, narrow decimal `always[...]` windows, and
  decimal inner stabilization windows.
- The twenty-ninth batch adds more `until[...]` responses whose terminators
  may be state predicates or `rise(...)` events over equality/range
  conditions.
- The twenty-ninth batch adds past-response variants including
  `not(once[...](fall(...)))`, plus temporal-input
  `not fall(eventually[...](...))` where the modifier scope remains over the
  complete eventuality.
- The twenty-ninth batch expands mixed trigger/response compositions:
  event-plus-state triggers, OR triggers over states/events/event absence,
  immediate OR responses mixing events and states, and negated predicate
  conjunctions.
- The thirtieth batch adds whole-expression negation over bounded
  `until[...]`, bounded `eventually[...]`, and unbounded `since(...)`
  temporal responses while preserving the full temporal scope of negation.
- The thirtieth batch expands temporal triggers: bounded
  `eventually[...]` triggers, bounded `always[...]` triggers, bounded
  `since[...]` triggers with decimal past windows, and `fall(historically(...))`
  triggers.
- The thirtieth batch adds additional `fall(...)` over complete
  `until[...]` responses, including nonzero bounded `until[...]` windows and
  negated terminators.
- The thirtieth batch expands recurrence/stabilization with
  `always(eventually[...](...))`, `always[...](eventually[...](...))`,
  `eventually[...](always(...))`, and delayed
  `eventually[...](always[...](...))`.
- The thirtieth batch expands mixed invariance/reachability/immediate
  targets involving event absence, negated ranges, decimal thresholds, OR
  enum targets, and conjunctions of events with states.
- The thirty-first batch adds temporal-input modifiers over complete past
  formulas, including `fall(since[...](...))`,
  `fall(since(...))`, and `not rise(once(...))`.
- The thirty-first batch expands historical and past-response handling with
  bounded `historically[...]` responses, bounded `historically[...]`
  triggers, and unbounded `once(...)` triggers that feed recurrence.
- The thirty-first batch adds whole-expression negation over delayed bounded
  `always[...]` responses, preserving the bounded always scope.
- The thirty-first batch expands `until` responses with event-absence left
  sides, reversed English order where the terminator is stated first, and
  event terminators such as `fall(...)`.
- The thirty-first batch expands recurrence/stabilization with dual-event
  triggers, delayed outer `always[...]` windows, delayed
  `eventually[...](always(...))`, and unbounded
  `always(eventually(...))` event recurrence.
- The thirty-second batch expands whole-expression negation over bounded
  `eventually[...]`, bounded `always[...]`, and nonzero bounded
  `until[...]` responses.
- The thirty-second batch adds more event-absence triggers and responses,
  including `not fall(...)` over ranges/equalities and OR triggers mixing
  event absence with ordinary state predicates.
- The thirty-second batch expands delayed and decimal timing with nonzero
  `always[...]`, nonzero `eventually[...]`, large nonzero `until[...]`,
  and nested delayed `eventually[...](always[...](...))` windows.
- The thirty-second batch adds past and historical variants such as bounded
  `once[...]` event triggers and bounded `historically[...]` responses over
  negated predicates.
- The thirty-second batch expands mixed immediate and reachability targets
  containing AND/OR state compositions, rise/fall events, negated ranges, and
  dual rise-event triggers.
- The thirty-third batch adds `since[...]` triggers feeding both recurrence
  and `since[...]` responses, including decimal past windows and large
  bounded past anchors.
- The thirty-third batch expands temporal triggers and responses involving
  whole-expression negation over `since(...)`, `not fall(eventually[...](...))`,
  and `fall(historically[...](...))`.
- The thirty-third batch adds more `until[...]` responses with large bounded
  windows, nonzero/decimal windows, event terminators, event-absence left
  sides, and cases where English states the terminator before the left
  condition.
- The thirty-third batch expands recurrence/stabilization with very large
  delayed outer windows, large/decimal inner windows, unbounded inner
  eventuality, and bounded `once[...]` triggers.
- The thirty-third batch expands mixed invariance, immediate, and
  reachability targets containing event absence under `always[...]`, OR
  event/state responses, dual event triggers, negated ranges, and rise/fall
  events over enum/range predicates.
- The thirty-fourth batch adds further whole-expression negation patterns
  over bounded `eventually[...]`, bounded `until[...]`, and delayed bounded
  `until[...]` formulas, including terminator-first English order.
- The thirty-fourth batch expands temporal-input event modifiers with
  `fall(always[...](...))`, `rise(since(...))`, and `fall(until[...](...))`
  while preserving modifier scope over the complete temporal expression.
- The thirty-fourth batch adds large and decimal timing variants: very
  delayed `eventually[...]`, very delayed `always[...]`, decimal nonzero
  bounded eventuality, and very large inner `always[...]` windows.
- The thirty-fourth batch expands recurrence/stabilization with
  `eventually(always(...))`, `eventually(always[...](...))`,
  `always(eventually[...](...))`, and `always[...](eventually[...](...))`.
- The thirty-fourth batch expands mixed immediate and reachability targets
  using event absence, OR event/state targets, dual rise events, fall events,
  negated ranges, and conjunctions of enum/equality responses.
- The thirty-fifth batch expands temporal-input triggers and modifiers with
  negated `historically(...)`, `rise(historically(...))`,
  `rise(eventually(...))`, and whole negation over large bounded
  `historically[...]` formulas.
- The thirty-fifth batch adds `until[...]` structures used both as triggers
  and responses, including bounded until triggers, nonzero bounded until
  responses, terminator-first English order, and since/ until combinations.
- The thirty-fifth batch expands past-response variants with bounded
  `once[...]` event responses and bounded `since[...]` responses anchored by
  `rise(...)` events.
- The thirty-fifth batch expands recurrence/stabilization with very large
  bounded eventual stabilization, delayed decimal inner `always[...]`
  windows, nonzero inner eventuality windows, and unbounded
  `eventually(always(...))` forms.
- The thirty-fifth batch expands immediate/reachability/invariance targets
  with event absence, OR event/state targets, mixed event-state eventuality,
  negated predicates, decimal ranges, and short/large bounded windows.
- The thirty-sixth batch adds temporal triggers including bounded
  `always[...]`, very delayed bounded `always[...]`, unbounded
  `always(...)`, and unbounded `since(...)` feeding recurrence/stabilization.
- The thirty-sixth batch expands temporal-input modifiers and negation with
  `not rise(eventually[...](...))`, `rise(historically(...))`, whole negation
  over large bounded `historically[...]`, and event-absence requirements
  inside bounded eventuality.
- The thirty-sixth batch adds past-response patterns with very large bounded
  `once[...]` over rise events and bounded `since[...]` responses anchored by
  rise events.
- The thirty-sixth batch expands recurrence/stabilization with unbounded
  `always(eventually(...))`, unbounded `eventually(always(...))`, large
  delayed bounded recurrence, large bounded eventual stabilization, and
  negated predicates inside sustained windows.
- The thirty-sixth batch expands mixed invariance/reachability/immediate
  targets containing event absence, OR event/state responses, conjunctions of
  events and states, decimal windows, and large delayed bounded eventuality.
- The thirty-seventh batch adds recurrence/stabilization variants with
  `always(eventually[...](...))`, `always(eventually(...))`,
  `eventually(always(...))`, and bounded eventual stabilization whose sustained
  condition is event absence such as `always[...](not rise(...))` or
  `always[...](not fall(...))`.
- The thirty-seventh batch expands temporal triggers from bounded
  `since[...]`, unbounded `since(...)`, bounded `once[...]`, bounded
  `historically[...]`, and bounded `always[...]` formulas.
- The thirty-seventh batch adds past-response variants with large bounded
  `once[...]` windows, bounded `since[...]` responses anchored by rise events,
  and bounded `once[...]` triggers over event absence.
- The thirty-seventh batch expands whole-expression negation over bounded and
  unbounded `until(...)` responses, including nonzero decimal bounded until
  windows and terminator-first English order.
- The thirty-seventh batch expands mixed invariance/reachability/immediate
  targets with event absence, negated state predicates, OR state/event
  targets, conjunctions of rise events with states, narrow decimal windows,
  and large bounded windows.
- The thirty-eighth batch expands event-absence handling inside temporal
  responses, including bounded `until[...]` with event-absence left sides and
  `not rise(...)` terminators.
- The thirty-eighth batch adds temporal-input modifiers such as
  `fall(until(...))` and since-triggered bounded `until[...]` responses,
  preserving the modifier scope over complete temporal formulas.
- The thirty-eighth batch expands past-trigger patterns with unbounded
  `once(...)` over fall events, bounded `once[...]` triggers with decimal and
  nonzero windows, and bounded `since[...]` triggers anchored by fall events.
- The thirty-eighth batch expands recurrence/stabilization with unbounded
  `always(eventually[...](...))`, unbounded
  `always(eventually(...))`, very delayed bounded `always[...]` recurrence,
  and delayed `eventually(always(...))` stabilization.
- The thirty-eighth batch expands invariance/reachability/immediate targets
  with large and decimal windows, OR state/event-absence triggers, fall/rise
  event responses, mixed event-state eventuality, and negated ranges.
- The thirty-ninth batch expands event-absence invariance with bounded
  `always[...]` over `not fall(...)` and `not rise(...)` requirements.
- The thirty-ninth batch adds temporal-input negation and modifiers including
  `not rise(historically[...](...))`, whole negation over bounded
  `always[...]`, whole negation over unbounded `eventually(...)`, and whole
  negation over bounded `until[...]`.
- The thirty-ninth batch expands temporal triggers with unbounded
  `since(...)`, bounded `once[...]`, very delayed bounded `always[...]`, and
  decimal bounded `once[...]` formulas.
- The thirty-ninth batch expands recurrence/stabilization with large bounded
  eventual stabilization, large inner eventuality windows, nonzero inner
  recurrence windows, event-absence sustained windows, and very delayed
  bounded recurrence.
- The thirty-ninth batch expands mixed invariance/reachability/immediate
  targets with event/state conjunctions, immediate rise/fall event responses,
  OR state targets, negated ranges, decimal thresholds, and large bounded
  windows.
- The fortieth batch expands temporal negation with whole negation over
  unbounded `always(...)`, bounded `eventually[...]`, bounded
  `always[...]`, bounded `since[...]`, and large nonzero bounded
  `once[...]` triggers.
- The fortieth batch adds temporal-input modifiers such as
  `not rise(eventually[...](...))` and `fall(always[...](...))`, preserving
  modifier scope over the complete temporal formula.
- The fortieth batch expands binary temporal responses with unbounded and
  bounded `until[...]`, large nonzero bounded `since[...]`, and event
  terminators such as `fall(...)`.
- The fortieth batch expands recurrence/stabilization with nonzero bounded
  `once[...]` triggers, temporal `eventually[...]` triggers, very delayed
  inner `always[...]` windows, delayed eventual stabilization, and unbounded
  `always(eventually[...](...))` recurrence.
- The fortieth batch expands invariance/reachability/immediate targets with
  large/decimal windows, event absence, OR state/event responses, negated
  ranges, decimal thresholds, and conjunctions of state/rise/fall events.
- The forty-first batch expands temporal negation with whole negation over
  bounded `historically[...]` and large decimal bounded `since[...]`
  triggers.
- The forty-first batch adds temporal-input event modifiers such as
  `rise(always[...](...))`, plus bounded/unbounded `until[...]` responses
  triggered by bounded `since[...]` and negated range predicates.
- The forty-first batch expands past-looking structures with large bounded
  `historically[...]`, unbounded `historically(...)`, large bounded
  `once[...]`, and large nonzero bounded `since[...]` responses.
- The forty-first batch expands recurrence/stabilization with very delayed
  bounded recurrence, very delayed inner `always[...]` windows, event absence
  inside sustained windows, and short/large bounded eventual stabilization.
- The forty-first batch expands invariance/reachability/immediate targets
  with event absence, negated predicates, decimal ranges, OR state/event
  responses, mixed rise/fall event conjunctions, and large/decimal bounded
  windows.
- The forty-second batch adds temporal-input modifiers such as
  `rise(eventually[...](fall(...)))`,
  `fall(eventually[...](rise(...)))`, and
  `not rise(historically[...](...))`, with modifier scope preserved over the
  complete temporal subexpression.
- The forty-second batch expands past-looking triggers with whole negation
  over bounded `since[...]`, unbounded `since(...)` anchored by `rise(...)`,
  and unbounded `historically(...)` responses over numeric equality.
- The forty-second batch expands temporal responses with bounded
  `until[...]`, whole negation over bounded `eventually[...]`, and bounded
  `eventually[...]` responses followed by bounded or unbounded
  `always(...)`.
- The forty-second batch expands recurrence/stabilization with
  `always[...](eventually[...](...))`,
  `eventually[...](always[...](...))`, and
  `eventually[...](always(...))`, including negated interval/state targets
  and decimal/large windows.
- The forty-second batch expands invariance/reachability/immediate targets
  with bounded `always[...]` over event absence or mixed equality/state
  conjunctions, bounded/unbounded `eventually(...)` over events and mixed
  requirements, and immediate OR responses mixing event absence with states.
- The forty-second batch adds more immediate triggers formed from state
  conjunctions, event-plus-state conjunctions, negated predicates, and rise or
  fall events over equality/range predicates.
- The forty-third batch adds whole-expression negation over unbounded
  `since(...)` triggers, plus bounded `since[...]` triggers feeding bounded
  `until[...]` responses.
- The forty-third batch expands temporal triggers with bounded
  `historically[...]`, unbounded `once(...)`, bounded `once[...]`, bounded
  `until[...]`, and whole negation over bounded `historically[...]` event
  absence.
- The forty-third batch expands `until[...]` responses with event-absence
  left sides, rise-event terminators, nonzero windows, decimal windows, and
  terminator-first English order.
- The forty-third batch expands recurrence/stabilization with
  `always[...](eventually[...](...))`,
  `always[...](eventually(...))`,
  `always(eventually(rise(...)))`,
  `eventually[...](always[...](...))`, and
  `eventually(always[...](...))`.
- The forty-third batch adds more delayed and decimal timing cases, including
  short decimal `always[...]` windows, decimal bounded reachability, very
  large sustained windows, and large decimal inner recurrence windows.
- The forty-third batch expands mixed invariance, reachability, and immediate
  targets with OR state/event targets, OR state/rise-event triggers, negated
  range predicates, event-absence responses, and conjunctions of numeric or
  mode states.
- The forty-fourth batch adds temporal-input modifiers over complete
  temporal subexpressions, including `not fall(eventually[...](not fall(...)))`,
  `rise(once[...](...))`, and `fall(eventually[...](rise(...)))`.
- The forty-fourth batch expands past-looking triggers and responses with
  bounded `since[...]`, bounded `once[...]`, unbounded `historically(...)`,
  and bounded `historically[...]` over negated predicates or event absence.
- The forty-fourth batch expands `until[...]` with event-absence left sides,
  rise-event terminators, negated-state terminators, nonzero decimal
  deadlines, unbounded until responses, and terminator-first English order.
- The forty-fourth batch expands recurrence/stabilization with
  `always[...](eventually[...](...))`,
  `always(eventually[...](...))`,
  `eventually[...](always[...](...))`,
  `eventually[...](always(...))`, and `eventually(always(...))`.
- The forty-fourth batch adds more large/decimal timing variants, including
  very delayed bounded always responses, large decimal bounded eventuality,
  decimal outer recurrence, nonzero inner recurrence, and large sustained
  always windows.
- The forty-fourth batch expands mixed invariance/reachability/immediate
  targets with event/state conjunctions, event-absence OR targets, dual-event
  OR responses, rise/fall event responses, negated ranges, and numeric/mode
  equality conjunctions.
- The forty-fifth batch adds temporal-input modifiers over complete
  subexpressions, including `rise(until[...](...))`,
  `not rise(eventually[...](rise(...)))`,
  `not rise(once[...](...))`, and `not fall(since(...))`.
- The forty-fifth batch expands temporal triggers with bounded
  `always[...]`, bounded `historically[...]`, bounded `since[...]`, whole
  negation over bounded `historically[...]`, and state/event conjunctions.
- The forty-fifth batch expands past responses with unbounded `once(...)`
  over negated predicates and bounded `historically[...]` over large past
  windows.
- The forty-fifth batch expands recurrence/stabilization with
  `always[...](eventually(...))`,
  `always[...](eventually[...](...))`,
  `always(eventually(...))`,
  `eventually(always[...](...))`, and `eventually[...](always[...](...))`.
- The forty-fifth batch adds more delayed and decimal timing cases, including
  very large bounded always antecedents, very delayed bounded eventuality,
  very short decimal inner recurrence windows, and large decimal sustained
  windows.
- The forty-fifth batch expands mixed invariance/reachability/immediate
  targets with OR state/range predicates, mixed state/rise-event reachability,
  event-absence targets, negated mode/range responses, and fall/rise events
  over numeric, enum, and interval predicates.
- The forty-sixth batch expands temporal-input modifiers over full
  subexpressions, including `fall(until(...))`,
  `fall(since[...](...))`, and whole negation over bounded `always[...]`
  responses.
- The forty-sixth batch adds past-looking triggers with bounded
  `since[...]` and bounded `historically[...]`, including decimal windows,
  anchor-first wording, and negated predicates inside the past formula.
- The forty-sixth batch expands recurrence/stabilization with
  `always(eventually[...](...))`,
  `always[...](eventually(...))`,
  `always[...](eventually[...](...))`,
  `eventually(always(...))`,
  `eventually(always[...](...))`, and
  `eventually[...](always[...](...))`.
- The forty-sixth batch adds large and decimal timing variants, including
  very delayed bounded eventuality, nonzero outer and inner recurrence
  windows, very short decimal inner windows, and nonzero bounded sustained
  windows.
- The forty-sixth batch expands invariance/reachability/immediate targets
  with negated-state conjunctions, mixed event/state conjunctions, OR
  threshold invariance, event-absence invariance, and immediate responses over
  negated ranges or mixed state/event outputs.
- The forty-seventh batch adds whole-expression temporal negation over
  bounded `once[...]`, bounded `always[...]`, unbounded `eventually(...)`, and
  bounded `historically[...]`, preserving scope over the complete temporal
  formula.
- The forty-seventh batch expands temporal-input modifiers with
  `rise(until[...](...))`, `not rise(eventually(...))`,
  `fall(historically(...))`, and `fall(historically(not ...))`.
- The forty-seventh batch expands temporal antecedents with bounded
  `always[...]`, bounded `until[...]`, bounded `once[...]`, bounded
  `historically[...]`, and unbounded `since(...)` anchored by rise events.
- The forty-seventh batch expands `until[...]` responses with negated
  threshold left sides, state terminators, rise-event terminators, nonzero
  windows, and terminator-first English order.
- The forty-seventh batch expands recurrence/stabilization with
  `always(eventually(...))`,
  `always(eventually[...](...))`,
  `always[...](eventually[...](...))`,
  `eventually(always[...](...))`, and
  `eventually[...](always[...](...))`.
- The forty-seventh batch adds more mixed invariance/reachability/immediate
  targets, including mode/range conjunctions, OR range/state targets, OR
  rise-event targets, mixed state/rise-event reachability, and immediate
  event/state conjunctions.
- The forty-eighth batch adds whole-expression temporal negation over
  unbounded `historically(...)`, plus temporal triggers formed from bounded
  `eventually[...]`, bounded `once[...]`, unbounded `until(...)`, and
  bounded/unbounded historical formulas.
- The forty-eighth batch expands temporal-input modifiers with
  `fall(since(...))` and keeps negation/modifier scope over the complete
  temporal expression.
- The forty-eighth batch expands `until[...]` and unbounded `until(...)`
  responses with state, range, negated-state, and fall-event terminators,
  including decimal deadlines and terminator-first English order.
- The forty-eighth batch expands recurrence/stabilization with
  `always[...](eventually(...))`,
  `always[...](eventually[...](...))`,
  `eventually[...](always(...))`, and
  `eventually[...](always[...](...))`, including very delayed inner
  recurrence windows.
- The forty-eighth batch adds additional mixed invariance/reachability and
  immediate-response targets with OR event/state triggers, negated state/range
  triggers, event-absence responses, and conjunctions or disjunctions of
  numeric thresholds, mode predicates, and rise/fall events.
- The forty-ninth batch expands whole-expression temporal negation and
  modifiers with `not(once[...](...))`,
  `not fall(always[...](...))`, `fall(always[...](...))`,
  `not(eventually(...))`, and `not(until(...))`.
- The forty-ninth batch expands temporal triggers from bounded/unbounded
  `eventually(...)`, bounded `historically[...]`, bounded `once[...]`, and
  bounded `since[...]`, including large and decimal windows.
- The forty-ninth batch adds bounded `once[...]` event responses and
  unbounded eventuality triggers followed by bounded past responses.
- The forty-ninth batch expands `until[...]` responses with nonzero windows,
  negated threshold left sides, state terminators, and temporal-triggered
  recurrence responses.
- The forty-ninth batch expands recurrence/stabilization with
  `always(eventually(...))`,
  `always[...](eventually(...))`,
  `always[...](eventually[...](...))`,
  `eventually[...](always[...](...))`, and
  `eventually[...](always(...))`, including very large delayed outer windows
  and nonzero decimal inner windows.
- The forty-ninth batch expands mixed invariance/reachability/immediate
  targets with OR rise-event targets, event/state conjunctions, negated mode
  states, event-absence targets, and numeric/range predicates with decimal
  bounds.
- The fiftieth batch adds temporal-input modifiers over complete formulas,
  including `not fall(always(...))`, `not fall(always[...](...))`, and
  `not fall(until[...](...))`, with modifier scope preserved.
- The fiftieth batch expands whole-expression temporal negation over bounded
  `historically[...]`, bounded `until[...]`, unbounded `eventually(...)`, and
  unbounded `historically(...)`.
- The fiftieth batch expands past-looking responses with unbounded
  `historically(...)`, bounded `since[...]` anchored by fall events, and
  unbounded `once(...)` triggers over fall events.
- The fiftieth batch expands `until[...]` and unbounded `until(...)`
  responses with event-absence or fall-event terminators, very delayed decimal
  windows, and negated-state left sides.
- The fiftieth batch expands recurrence/stabilization with
  `always[...](eventually(...))`,
  `always[...](eventually[...](...))`,
  `eventually[...](always[...](...))`, and very delayed
  `eventually[...](always[...](not fall(...)))` sustained event-absence
  windows.
- The fiftieth batch adds more mixed invariance/reachability/immediate
  targets, including unbounded eventually over rise events, OR state/rise
  triggers, dual rise-event triggers, event/state conjunctions, negated
  states/ranges, and decimal interval predicates.
- The fifty-first batch expands bounded and unbounded `until` responses with
  rise-event triggers, state/range left sides, state or rise-event
  terminators, large decimal deadlines, and terminator-first English order.
- The fifty-first batch adds past-looking triggers using bounded
  `historically[...]`, unbounded `historically(...)`, bounded `once[...]`,
  bounded `since[...]`, whole negation over bounded `since[...]`, and
  rise-modified bounded `since[...]` formulas.
- The fifty-first batch expands recurrence/stabilization with
  `always[...](eventually(...))`,
  `always[...](eventually[...](...))`,
  `always(eventually(...))`, and
  `eventually[...](always[...](...))`, including very large outer windows,
  short decimal windows, and sustained event-absence requirements.
- The fifty-first batch adds invariance/reachability cases with delayed
  bounded eventually, unbounded eventually, bounded always over events or
  mixed states, OR state/range targets, and mixed state/rise-event
  conjunctions.
- The fifty-first batch expands immediate responses with rise and fall
  triggers over equality, threshold, and interval predicates, including
  immediate event responses and OR response predicates.
- The fifty-second batch adds whole-expression temporal triggers and modifier
  cases, including bounded `until[...]` used as a trigger,
  `not rise(always(...))`, `not rise(until[...](...))`,
  `not fall(once[...](...))`, whole negation over bounded `once[...]`, and
  whole negation over bounded `since[...]`.
- The fifty-second batch expands past-looking antecedents with bounded
  `since[...]` anchored by negated states or rise events and unbounded
  `historically(...)` state triggers feeding bounded eventually or bounded
  until responses.
- The fifty-second batch expands recurrence/stabilization with
  `eventually[...](always(...))`,
  `eventually[...](always[...](...))`,
  `always(eventually[...](...))`,
  `always[...](eventually(...))`, and
  `always[...](eventually[...](...))`, including large delayed windows and
  nonzero decimal inner windows.
- The fifty-second batch adds temporal responses with bounded always over
  state/range predicates, bounded eventually over negated predicates, bounded
  and unbounded always responses, and bounded until responses with
  event-absence or state left sides.
- The fifty-second batch expands invariance/reachability and immediate cases
  with unbounded always threshold invariance, bounded eventually with decimal
  windows, OR triggers combining states and events, conjunction outputs, OR
  outputs, and immediate event-absence responses.
- The fifty-third batch expands temporal triggers over full temporal
  subexpressions, including bounded `always[...]`, unbounded `always(...)`,
  bounded `until[...]`, bounded `since[...]`, and temporal-input
  `not fall(eventually(...))`.
- The fifty-third batch adds temporal responses using bounded and unbounded
  `since` responses, bounded `historically[...]` past responses, whole
  negation over bounded `always[...]`, and `rise(until[...](...))` as an
  event response.
- The fifty-third batch expands recurrence/stabilization with
  `always[...](eventually[...](...))`,
  `always[...](eventually(...))`,
  `eventually[...](always(...))`, and
  `eventually[...](always[...](...))`, including very delayed outer windows,
  very short inner windows, and event or state inner targets.
- The fifty-third batch adds more bounded and unbounded invariance/reachability
  targets with OR state/range predicates, outside-range negation, decimal
  delayed reachability, and large bounded always windows.
- The fifty-third batch expands immediate responses with mixed state/event
  triggers, event responses, event-absence responses, OR event outputs, and
  outside-range immediate outputs.
- The fifty-fourth batch expands temporal modifiers over complete temporal
  formulas, including `not fall(until[...](...))`,
  `rise(always[...](...))`, and whole negation over unbounded
  `until(...)`.
- The fifty-fourth batch adds temporal triggers using unbounded `since(...)`,
  bounded `since[...]`, bounded `once[...]`, bounded `eventually[...]`, and
  unbounded `historically(...)` over event-absence predicates.
- The fifty-fourth batch expands `until[...]` and unbounded `until(...)`
  responses with nonzero future windows, state or negated-state left sides,
  state terminators, and terminator-first English order.
- The fifty-fourth batch expands recurrence/stabilization with
  `always(eventually[...](...))`,
  `always(eventually(...))`,
  `always[...](eventually(...))`,
  `always[...](eventually[...](...))`,
  `eventually(always[...](...))`, and
  `eventually[...](always(...))`.
- The fifty-fourth batch adds invariance/reachability and immediate cases with
  delayed bounded eventually, OR targets, event-absence/state conjunctions,
  immediate not-fall event absence, and mixed state/rise-event OR triggers.
- The fifty-fifth batch adds temporal modifiers over bounded past and future
  formulas, including `not(once[...](...))`,
  `not fall(until[...](...))`, `rise(once[...](...))`,
  `rise(eventually[...](...))`, and `rise(until[...](...))`.
- The fifty-fifth batch expands temporal triggers with event-absence triggers,
  bounded `since[...]`, bounded `historically[...]`, and whole bounded
  `until[...]` conditions detected as rising events.
- The fifty-fifth batch expands temporal responses with bounded
  `historically[...]`, bounded and unbounded `always` responses, whole
  negation over unbounded `always(...)`, bounded eventually over outside-range
  predicates, and bounded `until[...]` responses with large decimal deadlines.
- The fifty-fifth batch expands recurrence/stabilization with
  `always[...](eventually[...](...))`,
  `always(eventually[...](...))`,
  `eventually(always[...](...))`,
  `eventually[...](always[...](...))`, and
  `eventually[...](always(...))`.
- The fifty-fifth batch adds invariance/reachability and immediate variants
  with OR state/event targets, event-absence disjunctions, range conjunctions,
  mixed event/state immediate outputs, and very delayed bounded invariance.
- The fifty-sixth batch expands whole-expression temporal negation with
  bounded `historically[...]`, bounded `once[...]`, and bounded
  `eventually[...]`, including negated past/event conditions used as temporal
  responses.
- The fifty-sixth batch adds temporal-input modifiers with
  `fall(historically[...](...))` and unbounded `once(...)` triggers over rise
  events.
- The fifty-sixth batch expands recurrence/stabilization with
  `always[...](eventually(...))`,
  `always(eventually[...](...))`,
  `eventually(always[...](...))`,
  `eventually[...](always(...))`, and
  `eventually[...](always[...](...))`, including nonzero decimal sustained
  windows.
- The fifty-sixth batch adds more bounded/unbounded invariance and
  reachability with fall-event/state conjunctions, negated-state conjunctions,
  OR event/state targets, and event-absence invariance over delayed windows.
- The fifty-sixth batch expands immediate responses with negated triggers,
  fall triggers, OR triggers, event-absence OR outputs, and mixed event/state
  conjunction outputs.
- The fifty-seventh batch expands temporal-input modifiers over past and
  future formulas, including `fall(since(...))`,
  `rise(always[...](...))`, and `fall(eventually[...](...))`.
- The fifty-seventh batch adds temporal triggers using unbounded `once(...)`,
  bounded `once[...]`, bounded/unbounded `since`, bounded `always[...]`, and
  whole negation over large bounded `once[...]`.
- The fifty-seventh batch expands temporal responses with nonzero bounded
  `until[...]`, whole negation over bounded/unbounded eventuality,
  whole negation over bounded `since[...]`, and unbounded `since(...)`
  responses.
- The fifty-seventh batch expands recurrence/stabilization with
  `eventually(always(...))`,
  `always[...](eventually(...))`,
  `always[...](eventually[...](...))`,
  `eventually[...](always[...](...))`, and large bounded
  `always[...](eventually[...](...))` windows.
- The fifty-seventh batch adds invariance/reachability and immediate variants
  with unbounded event reachability, bounded OR state/event reachability,
  event-absence OR targets, dual-event triggers, and mixed event/state
  immediate responses.
- The fifty-eighth batch expands temporal modifiers over complete temporal
  formulas, including `fall(always[...](...))`,
  `fall(since(...))`, `not fall(until[...](...))`, and whole negation over
  delayed bounded `until[...]`.
- The fifty-eighth batch adds temporal triggers using unbounded `since(...)`,
  bounded `since[...]`, whole negated bounded `until[...]`, event-absence
  conjunctions, and mixed state/event antecedents.
- The fifty-eighth batch expands temporal responses with bounded and
  unbounded `until`, whole negation over bounded `always[...]` and
  `eventually[...]`, and bounded always responses with decimal windows.
- The fifty-eighth batch expands recurrence/stabilization with
  `always(eventually(...))`,
  `always(eventually[...](...))`,
  `always[...](eventually(...))`,
  `always[...](eventually[...](...))`,
  `eventually(always[...](...))`, and delayed
  `eventually[...](always[...](...))`.
- The fifty-eighth batch adds invariance/reachability and immediate variants
  with very large delayed intervals, event-absence invariance, unbounded fall
  reachability, OR event/state targets, and OR-triggered immediate
  conjunction outputs.
- The fifty-ninth batch expands temporal responses with past `once(...)`
  outputs, bounded `once[...]` outputs, bounded/unbounded `until` responses,
  bounded `always` responses, and whole negation over bounded
  `eventually[...]` and bounded `until[...]`.
- The fifty-ninth batch adds temporal triggers using unbounded
  `eventually(...)`, bounded `historically[...]`, event-absence OR
  antecedents, and mixed state/rise-event antecedents.
- The fifty-ninth batch expands recurrence/stabilization with
  `eventually(always[...](...))`,
  `eventually[...](always[...](...))`,
  `eventually(always(...))`,
  `always[...](eventually[...](...))`, and
  `always[...](eventually(...))`.
- The fifty-ninth batch adds invariance/reachability and immediate variants
  with unbounded mode conjunction reachability, very delayed bounded
  reachability, negated bounded invariance, mixed event/state immediate
  outputs, fall-event responses, and OR-triggered recurrence.
- The sixtieth batch adds temporal triggers using bounded `historically[...]`,
  bounded `once[...]`, bounded `until[...]`, unbounded `eventually(...)`,
  bounded `since[...]` under whole negation, and temporal-input
  `not fall(historically[...](...))`.
- The sixtieth batch expands temporal responses with bounded/unbounded
  `always`, bounded `historically[...]`, unbounded and bounded `once`
  responses, bounded/unbounded `until`, whole negation over bounded `once`,
  and bounded always responses carrying event-absence predicates.
- The sixtieth batch expands recurrence/stabilization with
  `always(eventually(...))`,
  `always(eventually[...](...))`,
  `eventually(always[...](...))`,
  `eventually[...](always[...](...))`, and
  `always[...](eventually[...](...))`, including large delayed and decimal
  windows.
- The sixtieth batch adds invariance/reachability and immediate variants with
  event-absence reachability, mixed event/state reachability, OR state/range
  targets, OR-triggered immediate responses, and mixed event/state immediate
  outputs.
- The sixty-first batch adds temporal modifiers over full temporal formulas,
  including `fall(until(...))`, `rise(once(...))`,
  `rise(since(...))`, and whole negation over bounded/unbounded
  `always(...)`.
- The sixty-first batch expands temporal triggers with bounded
  `historically[...]`, bounded/unbounded `since`, unbounded `until`, bounded
  `once[...]`, and whole negation over bounded historical conditions.
- The sixty-first batch expands temporal responses with bounded/unbounded
  `until`, bounded `historically[...]`, bounded `since[...]`, bounded
  `once[...]`, unbounded eventuality responses, and bounded eventually over
  rise events.
- The sixty-first batch expands recurrence/stabilization with
  `eventually[...](always[...](...))`,
  `eventually(always(...))`,
  `eventually(always[...](...))`,
  `always(eventually[...](...))`,
  `always[...](eventually[...](...))`, and
  `always[...](eventually(...))`.
- The sixty-first batch adds invariance/reachability and immediate variants
  with very delayed bounded reachability, unbounded rise-event reachability,
  OR invariance, mixed state/event triggers, event-absence triggers, and
  conjunction outputs.
- The sixty-second batch expands temporal-input modifiers with
  `fall(until[...](...))`, `rise(once(...))`, and temporal antecedents built
  from bounded `always[...]`, unbounded `always(...)`, and bounded
  `eventually[...]`.
- The sixty-second batch adds bounded/unbounded past responses, including
  bounded `once[...]` to bounded `once[...]`, bounded `always[...]` to
  bounded `once[...]`, and bounded/unbounded `since` responses.
- The sixty-second batch expands temporal responses with whole negation over
  bounded `always[...]`, bounded and unbounded `until`, bounded/unbounded
  eventually, and long bounded always responses.
- The sixty-second batch expands recurrence/stabilization with
  `eventually[...](always[...](...))`,
  `eventually(always[...](...))`,
  `eventually(always(...))`,
  `always(eventually(...))`,
  `always(eventually[...](...))`, and
  `always[...](eventually[...](...))`.
- The sixty-second batch adds invariance/reachability and immediate variants
  with delayed rise-event reachability, OR invariance, event-absence
  invariance, mixed event/state reachability, conjunction outputs, and
  immediate fall/rise event responses.
- The sixty-third batch expands triggers with rise/fall interval-entry and
  interval-exit events, mixed event/state antecedents, OR event antecedents,
  unbounded `once(...)`, bounded `once[...]`, unbounded `historically(...)`,
  and bounded `until[...]` temporal antecedents.
- The sixty-third batch expands temporal responses with bounded `until[...]`
  where the terminating side may be a rise event or a range predicate, bounded
  `always[...]` state responses, bounded `eventually[...]` event responses,
  and whole negation over bounded eventuality or unbounded always responses.
- The sixty-third batch expands recurrence/stabilization with
  `eventually[...](always[...](...))`,
  `eventually(always[...](...))`,
  `eventually[...](always(...))`,
  `always(eventually(...))`, and
  `always[...](eventually[...](...))`, including delayed and decimal
  windows.
- The sixty-third batch adds invariance/reachability and immediate variants
  with unbounded rise/fall reachability, delayed bounded reachability,
  bounded conjunction and OR targets, short bounded windows, OR-triggered
  immediate conjunction outputs, and immediate negated threshold responses.
- The sixty-fourth batch expands temporal triggers with bounded/unbounded
  `since`, bounded `once[...]`, bounded eventuality antecedents, temporal-input
  `not rise(since(...))`, not-rise event antecedents, and mixed state/event
  antecedents.
- The sixty-fourth batch expands temporal responses with bounded `always[...]`,
  bounded/unbounded `eventually`, bounded `until[...]`, bounded/unbounded
  `since`, whole negation over bounded always/even­tuality responses, and
  immediate fall/rise event outputs.
- The sixty-fourth batch expands recurrence/stabilization with
  `always(eventually(...))`, `always(eventually[...](...))`,
  `always[...](eventually[...](...))`, and large inner bounded eventuality
  windows.
- The sixty-fourth batch adds invariance/reachability variants with unbounded
  conjunction invariance, bounded event-absence invariance, OR bounded
  invariance, short/large bounded reachability, unbounded conjunction
  reachability, and decimal-window ranges.
- The sixty-fifth batch expands temporal triggers with bounded `until[...]`
  under rise, bounded `once[...]`, bounded `historically[...]`, whole negation
  over bounded historical predicates, OR state/event antecedents, and temporal
  modifiers over unbounded eventuality or always subformulas.
- The sixty-fifth batch expands temporal responses with bounded `until[...]`,
  delayed bounded `eventually[...]`, bounded `always[...]`, bounded
  `historically[...]`, unbounded `once(...)`, whole negation over unbounded
  always, and event-modifier responses such as `not fall(always(...))` and
  `fall(eventually(...))`.
- The sixty-fifth batch expands recurrence/stabilization with
  `eventually[...](always[...](...))`,
  `always[...](eventually[...](...))`, long bounded windows, delayed outer
  recurrence windows, and negated historical antecedents.
- The sixty-fifth batch adds invariance/reachability and immediate variants
  with unbounded rise-event OR reachability, bounded OR invariance, bounded
  negated invariance, state/event immediate conjunction outputs, and
  OR-triggered immediate conjunction responses.
- The sixty-sixth batch expands temporal triggers with whole negation over
  bounded `until[...]`, temporal `fall(since(...))`, event-absence triggers,
  OR event/state antecedents, and mixed state/rise antecedents.
- The sixty-sixth batch expands temporal responses with bounded and unbounded
  `until`, bounded and unbounded `since`, unbounded `once(...)`, whole
  negation over bounded eventuality, delayed bounded eventuality, and
  event-absence eventual reachability.
- The sixty-sixth batch expands recurrence/stabilization with
  `always(eventually[...](...))`,
  `always[...](eventually[...](...))`,
  `eventually[...](always[...](...))`,
  `eventually(always[...](...))`, and
  `eventually[...](always(...))`, including large delayed windows.
- The sixty-sixth batch adds invariance/reachability and immediate variants
  with unbounded OR reachability, bounded OR/conjunction reachability,
  bounded negated reachability, unbounded OR invariance, decimal bounded
  invariance, and immediate event/state conjunction outputs.
- The sixty-seventh batch expands temporal triggers with unbounded `since`,
  bounded `once[...]` over fall events, bounded `until[...]` antecedents,
  temporal-input `fall(always(...))`, and long bounded `always[...]`
  antecedents.
- The sixty-seventh batch expands temporal responses with unbounded and
  bounded `always`, unbounded and bounded `until`, bounded `since`, bounded
  `once[...]`, whole negation over bounded `eventually[...]`, and
  temporal-input `not rise(eventually(...))`.
- The sixty-seventh batch expands recurrence/stabilization with
  `always[...](eventually(...))`,
  `always[...](eventually[...](...))`,
  `eventually[...](always[...](...))`,
  `eventually(always[...](...))`, and
  delayed `eventually[...](always(...))`.
- The sixty-seventh batch adds invariance/reachability and immediate variants
  with event-absence reachability, OR event reachability, bounded delayed OR
  invariance, unbounded state invariance, OR-triggered immediate event
  outputs, and immediate event-absence conjunction responses.
- The sixty-eighth batch expands temporal triggers with rise over bounded
  `since[...]`, fall over unbounded `historically(...)`, bounded `once[...]`
  over fall events, OR state/event antecedents, and mixed event/state
  antecedents.
- The sixty-eighth batch expands temporal responses with bounded and unbounded
  `until`, bounded `since`, bounded `always[...]`, whole negation over
  bounded eventuality and bounded until responses, plus unbounded always
  responses over negated state/range predicates.
- The sixty-eighth batch expands recurrence/stabilization with
  `always(eventually[...](...))`,
  `always[...](eventually[...](...))`,
  `eventually[...](always[...](...))`,
  `eventually[...](always(...))`, and
  `always(eventually(...))` with event and state targets.
- The sixty-eighth batch adds invariance/reachability and immediate variants
  with bounded OR invariance, delayed bounded invariance, unbounded fall/rise
  reachability, bounded event/state reachability, immediate event/state
  conjunction outputs, and OR-triggered immediate range responses.
- The sixty-ninth batch expands temporal triggers with unbounded
  `historically(...)`, bounded `historically[...]`, rise and fall event
  antecedents, event-absence antecedents, OR state/event antecedents, and
  temporal-input `rise(once(...))`.
- The sixty-ninth batch expands temporal responses with bounded/unbounded
  `until`, bounded `since`, bounded `historically[...]`, bounded
  `always[...]`, whole negation over bounded eventually and bounded always
  responses, and event-absence immediate outputs.
- The sixty-ninth batch expands recurrence/stabilization with
  `eventually[...](always[...](...))`,
  `always[...](eventually[...](...))`,
  `always(eventually[...](...))`,
  `eventually[...](always(...))`, and
  `eventually(always[...](...))`.
- The sixty-ninth batch adds invariance/reachability and immediate variants
  with delayed OR reachability, decimal bounded always ranges, bounded
  event-absence invariance, unbounded negated-state invariance, OR-triggered
  immediate conjunctions, and state/event immediate disjunction outputs.
- The seventieth batch expands temporal triggers with bounded `once[...]`
  antecedents, bounded `since` triggers, fall/rise event triggers, event
  absence antecedents, and mixed event/state antecedents.
- The seventieth batch expands temporal responses with bounded/unbounded
  eventually, bounded always, bounded once-to-once past response, whole
  negation over bounded/unbounded eventuality, and bounded event-absence
  eventually responses.
- The seventieth batch expands recurrence/stabilization with
  `eventually[...](always[...](...))`,
  `always[...](eventually[...](...))`,
  `always[...](eventually(...))`, and
  `always(eventually(...))`, including decimal and very large bounded windows.
- The seventieth batch adds invariance/reachability and immediate variants
  with bounded event absence, delayed bounded reachability, OR invariance,
  bounded event/state reachability, unbounded OR invariance, and immediate
  event/state disjunction outputs.
- The seventy-first batch expands temporal triggers with bounded
  `historically[...]`, bounded `once[...]`, bounded `since[...]`,
  temporal-input `fall(since[...](...))`, and long bounded always antecedents.
- The seventy-first batch expands temporal responses with bounded/unbounded
  eventually, bounded/unbounded until, bounded/unbounded always, bounded
  historically, bounded once responses, whole negation over historical and
  eventuality responses, and temporal modifier responses.
- The seventy-first batch expands recurrence/stabilization with
  `eventually[...](always[...](...))`,
  `always[...](eventually[...](...))`,
  `always(eventually(...))`, delayed
  `eventually[...](always[...](...))`, and unbounded eventuality inside
  bounded recurrence.
- The seventy-first batch adds invariance/reachability and immediate variants
  with bounded OR/conjunction invariance, unbounded OR invariance, delayed
  bounded reachability, unbounded event-absence reachability, and immediate
  event/state disjunction outputs.
- Rows 3551–4050 were processed as the first 500-row batch after the batch-size
  change. The knowledge update was intentionally compact: no row trace, no
  confidence placeholders, and no statistical fields.
- Rows 3551–4050 reinforce mixed state/event invariance and reachability,
  immediate state/event/event-absence outputs, temporal triggers built from
  past and future subformulas, and whole-formula temporal negation.
- Rows 3551–4050 reinforce recurrence forms including
  eventually(always(...)), always(eventually(...)),
  eventually(always[...](...)), and always[...](eventually[...](...)).
- No per-row trace or evidence file was created.
- Rows 8051–8550 were processed as one 500-row batch. The update remains
  compact and semantic-only: no row trace, no confidence placeholders, and no
  statistical fields.
- Rows 8051–8550 add complete-formula event modifiers over past, future, and
  binary temporal subexpressions, including fall(historically(...)),
  fall(once(...)), fall(until[...](...)), fall(eventually[...](...)),
  rise(once[...](...)), rise(eventually(...)), not rise(always[...](...)),
  not rise(once[...](...)), not fall(historically(...)),
  not fall(always(...)), and not fall(since[...](...)).
- Rows 8051–8550 expand temporal responses where bounded or unbounded
  `historically`, `once`, `since`, and `until` formulas appear as triggers or
  consequents; negation and event-modifier scope is preserved over complete
  temporal subexpressions.
- Rows 8051–8550 reinforce stabilization/recurrence with delayed
  `eventually[...](always[...](...))`, unbounded
  `eventually[...](always(...))`, bounded
  `always[...](eventually[...](...))`, bounded
  `always[...](eventually(...))`, and unbounded
  `always(eventually[...](...))` or `always(eventually(...))`.
- Rows 8051–8550 reinforce invariance/reachability and immediate responses
  with mixed state/event conjunctions and disjunctions, delayed bounded
  reachability, unbounded reachability, event absence, not-rise/not-fall atoms,
  decimal windows, and large bounded intervals.
- Rows 8551–9050 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace, no confidence placeholders, and no
  statistical fields.
- Rows 8551–9050 add complete-formula modifiers over temporal subexpressions,
  including fall(historically(...)), fall(since[...](...)), fall(since(...)),
  rise(always[...](...)), rise(until[...](...)), not rise(always(...)),
  not rise(always[...](...)), not rise(since[...](...)),
  not fall(historically[...](...)), not fall(since(...)), and
  not fall(eventually(...)).
- Rows 8551–9050 expand temporal responses with whole-negated
  `eventually[...]`, `always[...]`, `always`, `since`, `since[...]`, `until`,
  and `until[...]` formulas; negation and event-modifier scope is preserved
  over the complete temporal subexpression.
- Rows 8551–9050 reinforce cross-time responses where `historically`,
  `historically[...]`, `once`, `once[...]`, `since`, `since[...]`, `until`,
  and `until[...]` appear as triggers or consequents for bounded always,
  bounded eventually, unbounded always, unbounded eventually, and
  bounded/unbounded until responses.
- Rows 8551–9050 reinforce stabilization/recurrence with large and decimal
  windows, including delayed `eventually[...](always[...](...))`,
  `eventually(always[...](...))`, `eventually(always(...))`,
  `always[...](eventually[...](...))`, `always[...](eventually(...))`,
  `always(eventually[...](...))`, and `always(eventually(...))`.
- Rows 8551–9050 reinforce invariance/reachability and immediate responses
  with unbounded and bounded invariance, delayed reachability, conjunction and
  disjunction requirements, event and event-absence targets, negated ranges,
  and same-instant mixed state/event outputs.
- Rows 9051–9550 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace, no confidence placeholders, and no
  statistical fields.
- Rows 9051–9550 add complete-formula modifiers over temporal subexpressions,
  including fall(always(...)), fall(always[...](...)),
  fall(historically(...)), fall(since[...](...)), fall(until[...](...)),
  rise(since[...](...)), rise(until[...](...)), not rise(since(...)),
  not rise(since[...](...)), not rise(until[...](...)),
  not fall(eventually(...)), not fall(eventually[...](...)),
  not fall(always[...](...)), and not fall(once[...](...)).
- Rows 9051–9550 expand whole-negated temporal responses and triggers over
  `once`, `once[...]`, `historically`, `historically[...]`, `since[...]`,
  `until`, `until[...]`, `always`, `always[...]`, `eventually`, and
  `eventually[...]`; scope is preserved over the complete temporal formula.
- Rows 9051–9550 reinforce cross-time pairings where past temporal formulas
  trigger bounded always, bounded eventually, bounded/unbounded until, bounded
  historically, bounded once, and stabilization/recurrence responses.
- Rows 9051–9550 reinforce stabilization/recurrence with long delayed
  windows, decimal windows, event targets, event-absence targets, and
  combinations such as `eventually[...](always[...](...))`,
  `eventually(always(...))`, `always[...](eventually[...](...))`,
  `always[...](eventually(...))`, and `always(eventually[...](...))`.
- Rows 9051–9550 reinforce invariance/reachability and immediate responses
  with unbounded invariance, bounded invariance, delayed reachability,
  state/event conjunctions, state/event disjunctions, negated ranges, and
  same-instant outputs containing rise, fall, not-rise, and not-fall atoms.
- Rows 9551–10050 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace, no confidence placeholders, and no
  statistical fields.
- Rows 9551–10050 add complete-formula modifiers over temporal subexpressions,
  including fall(once[...](...)), rise(eventually[...](...)),
  rise(until[...](...)), fall(until(...)), not rise(eventually(...)),
  not rise(until[...](...)), and not fall(eventually[...](...)).
- Rows 9551–10050 expand whole-negated temporal responses and triggers over
  `always`, `always[...]`, `eventually`, `eventually[...]`, `since[...]`,
  `until`, and `until[...]`; scope is preserved over the complete temporal
  formula.
- Rows 9551–10050 reinforce cross-time pairings where `historically`,
  `historically[...]`, `once`, `once[...]`, `since`, `since[...]`, `until`,
  and `until[...]` appear as triggers or consequents for bounded always,
  bounded eventually, unbounded always, unbounded eventually, bounded or
  unbounded until, bounded historically, and bounded once responses.
- Rows 9551–10050 reinforce stabilization/recurrence with long delayed
  windows, decimal windows, past-temporal antecedents, whole-temporal
  antecedents, event targets, event-absence targets, and combinations such as
  `eventually(always(...))`, `eventually[...](always[...](...))`,
  `always(eventually[...](...))`, and
  `always[...](eventually[...](...))`.
- Rows 9551–10050 reinforce invariance/reachability and immediate responses
  with bounded and unbounded invariance, delayed reachability, conjunction and
  disjunction requirements, negated ranges, and same-instant mixed outputs
  containing state predicates, mode predicates, rise, fall, not-rise, and
  not-fall atoms.
- Rows 10051–10550 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace, no confidence placeholders, and no
  statistical fields.
- Rows 10051–10550 add complete-formula modifiers over temporal subexpressions,
  including not fall(always[...](...)), not rise(always[...](...)),
  rise(always(...)), rise(always[...](...)), rise(since[...](...)),
  fall(eventually(...)), fall(historically(...)), not fall(until[...](...)),
  fall(until(...)), rise(historically(...)), and
  not rise(historically[...](...)).
- Rows 10051–10550 expand whole-negated temporal responses and triggers over
  `always`, `always[...]`, `eventually`, `eventually[...]`, `historically`,
  `historically[...]`, `once`, `once[...]`, `since`, `since[...]`, `until`,
  and `until[...]`; scope is preserved over the complete temporal formula.
- Rows 10051–10550 reinforce cross-time pairings where past temporal formulas
  trigger or answer with bounded/unbounded `until`, `since`, `historically`,
  `once`, bounded eventually, bounded always, and stabilization/recurrence
  responses.
- Rows 10051–10550 reinforce stabilization/recurrence with whole-negated
  antecedents, whole-temporal antecedents, long windows, decimal windows,
  event targets, event-absence targets, and combinations such as
  `eventually(always(...))`, `eventually(always[...](...))`,
  `always(eventually[...](...))`, and
  `always[...](eventually[...](...))`.
- Rows 10051–10550 reinforce invariance/reachability and immediate responses
  with mixed state/mode/range predicates, delayed reachability, event and
  event-absence targets, same-instant Boolean outputs, and negated range or
  mode predicates.
- Rows 10551–11050 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace, no confidence placeholders, and no
  statistical fields.
- Rows 10551–11050 add complete-formula modifiers over temporal
  subexpressions, including rise(eventually(...)), not fall(once(...)),
  fall(since(...)), fall(eventually(...)), rise(historically[...](...)),
  not fall(always(...)), fall(always(...)), not rise(until(...)),
  not fall(since[...](...)), fall(historically(...)), fall(until(...)), and
  fall(always[...](...)).
- Rows 10551–11050 expand whole-negated temporal responses and triggers over
  `always`, `always[...]`, `eventually`, `eventually[...]`,
  `historically[...]`, `once`, `once[...]`, `since`, `since[...]`, `until`,
  and `until[...]`; scope is preserved over the complete temporal formula.
- Rows 10551–11050 reinforce cross-time pairings where past and binary
  temporal formulas serve as triggers or consequents for past responses,
  bounded always responses, bounded or unbounded eventually responses,
  bounded or unbounded until responses, and stabilization/recurrence.
- Rows 10551–11050 reinforce stabilization/recurrence with long delayed
  windows, decimal windows, whole-negated antecedents, whole-temporal
  antecedents, event targets, event-absence targets, and combinations such as
  `always(eventually(...))`, `always[...](eventually[...](...))`,
  `eventually(always(...))`, and `eventually[...](always[...](...))`.
- Rows 10551–11050 reinforce invariance/reachability and immediate responses
  with event/state conjunctions and disjunctions, delayed reachability,
  bounded and unbounded invariance, event absence, negated ranges, and
  same-instant mixed outputs.
- Rows 11051–11550 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace and no confidence placeholders.
- Rows 11051–11550 add complete-formula modifiers over temporal
  subexpressions, including not rise(always(...)),
  not rise(eventually[...](...)), not rise(until[...](...)),
  rise(always(...)), rise(always[...](...)), rise(eventually(...)),
  fall(until[...](...)), not fall(eventually(...)),
  not fall(until(...)), not fall(until[...](...)),
  not fall(since[...](...)), and rise(historically[...](...)).
- Rows 11051–11550 expand whole-negated temporal responses and triggers over
  `always`, `always[...]`, `eventually`, `eventually[...]`,
  `historically[...]`, `once`, `once[...]`, `since`, `since[...]`, `until`,
  and `until[...]`; scope is preserved over the complete temporal formula.
- Rows 11051–11550 reinforce cross-time pairings where full past, future, and
  binary temporal formulas serve as triggers or consequents for past
  responses, bounded or unbounded eventually responses, bounded always
  responses, bounded or unbounded until responses, and recurrence structures.
- Rows 11051–11550 reinforce stabilization/recurrence with large windows,
  decimal windows, whole-negated antecedents, full-temporal antecedents, event
  targets, event-absence targets, sustained negated ranges, and combinations
  such as `always(eventually(...))`,
  `always[...](eventually[...](...))`, `eventually(always(...))`, and
  `eventually[...](always[...](...))`.
- Rows 11051–11550 reinforce invariance/reachability and immediate responses
  with bounded and unbounded invariance, delayed reachability, mode predicates,
  range predicates, event and event-absence targets, same-instant Boolean
  outputs, and negated state or range requirements.
- Rows 11551–12050 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace and no confidence placeholders.
- Rows 11551–12050 add complete-formula modifiers over temporal
  subexpressions, including not fall(always[...](...)),
  not fall(eventually[...](...)), not rise(always[...](...)),
  not rise(eventually[...](...)), rise(always[...](...)),
  rise(eventually[...](...)), rise(historically[...](...)),
  rise(until[...](...)), fall(once(...)), fall(once[...](...)),
  fall(since(...)), fall(historically(...)), and fall(until[...](...)).
- Rows 11551–12050 expand whole-negated temporal responses and triggers over
  `always`, `always[...]`, `eventually`, `eventually[...]`, `historically`,
  `historically[...]`, `once`, `once[...]`, `since`, `since[...]`, `until`,
  and `until[...]`; scope is preserved over the complete temporal formula.
- Rows 11551–12050 reinforce cross-time pairings where full past, future, and
  binary temporal formulas serve as triggers or consequents for past
  responses, future responses, binary-temporal responses, and recurrence
  structures.
- Rows 11551–12050 reinforce stabilization/recurrence with long delayed
  windows, decimal windows, full-temporal antecedents, whole-negated
  antecedents, event targets, event-absence targets, sustained negated
  state/range targets, and combinations such as
  `always(eventually[...](...))`, `always[...](eventually[...](...))`,
  `eventually(always[...](...))`, and `eventually[...](always(...))`.
- Rows 11551–12050 reinforce invariance/reachability and immediate responses
  with bounded and unbounded invariance, delayed reachability, same-instant
  event/state mixtures, mode predicates, open/closed ranges, event absence,
  and negated state or range requirements.
- Rows 12051–12550 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace and no confidence placeholders.
- Rows 12051–12550 add complete-formula modifiers over temporal
  subexpressions, including fall(eventually[...](...)), fall(always(...)),
  fall(always[...](...)), rise(until[...](...)),
  not rise(always[...](...)), not rise(historically(...)),
  not fall(always(...)), and not fall(until[...](...)).
- Rows 12051–12550 expand whole-negated temporal responses and triggers over
  `always`, `always[...]`, `eventually`, `eventually[...]`,
  `historically[...]`, `once[...]`, `since[...]`, `until`, and
  `until[...]`; scope is preserved over the complete temporal formula.
- Rows 12051–12550 reinforce cross-time pairings where full past, future, and
  binary temporal formulas serve as triggers or consequents for past
  responses, future responses, binary-temporal responses, and recurrence
  structures.
- Rows 12051–12550 reinforce stabilization/recurrence with delayed windows,
  decimal windows, full-temporal antecedents, whole-negated antecedents, event
  targets, event-absence targets, sustained negated state/range targets, and
  combinations such as `always(eventually[...](...))`,
  `always[...](eventually[...](...))`, `eventually(always[...](...))`, and
  `eventually[...](always(...))`.
- Rows 12051–12550 reinforce invariance/reachability and immediate responses
  with bounded and unbounded invariance, delayed reachability, same-instant
  event/state mixtures, mode predicates, open/closed ranges, event absence,
  and negated state or range requirements.
- Rows 12551–13050 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace and no confidence placeholders.
- Rows 12551–13050 add complete-formula modifiers over temporal
  subexpressions, including rise(always(...)), rise(always[...](...)),
  rise(eventually[...](...)), fall(eventually(...)),
  fall(eventually[...](...)), fall(always(...)), fall(always[...](...)),
  fall(until[...](...)), fall(once[...](...)), not fall(once(...)),
  not fall(since[...](...)), not fall(until(...)),
  not rise(historically[...](...)), not rise(since[...](...)),
  not rise(always(...)), and not rise(always[...](...)).
- Rows 12551–13050 expand whole-negated temporal responses and triggers over
  `always`, `always[...]`, `eventually`, `eventually[...]`,
  `historically[...]`, `once`, `once[...]`, `since`, `since[...]`, `until`,
  and `until[...]`; scope is preserved over the complete temporal formula.
- Rows 12551–13050 reinforce cross-time pairings where full past, future, and
  binary temporal formulas serve as triggers or consequents for past
  responses, future responses, binary-temporal responses, and recurrence
  structures.
- Rows 12551–13050 reinforce stabilization/recurrence with delayed windows,
  decimal windows, full-temporal antecedents, whole-negated antecedents, event
  targets, event-absence targets, sustained negated state/range targets, and
  combinations such as `always(eventually[...](...))`,
  `always[...](eventually[...](...))`, `eventually(always[...](...))`, and
  `eventually[...](always(...))`.
- Rows 12551–13050 reinforce invariance/reachability and immediate responses
  with bounded and unbounded invariance, delayed reachability, same-instant
  event/state mixtures, mode predicates, open/closed ranges, event absence,
  and negated state or range requirements.
- Rows 13051–13550 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace and no confidence placeholders.
- Rows 13051–13550 add complete-formula modifiers over temporal
  subexpressions, including rise(historically[...](...)),
  fall(historically(...)), fall(since(...)), fall(until(...)),
  not fall(always[...](...)), not fall(eventually[...](...)),
  not fall(historically[...](...)), and not rise(until[...](...)).
- Rows 13051–13550 expand whole-negated temporal responses and triggers over
  `always`, `always[...]`, `eventually`, `eventually[...]`,
  `historically[...]`, `once`, `once[...]`, `since`, `since[...]`, `until`,
  and `until[...]`; scope is preserved over the complete temporal formula.
- Rows 13051–13550 reinforce cross-time pairings where full past, future, and
  binary temporal formulas serve as triggers or consequents for past
  responses, future responses, binary-temporal responses, and recurrence
  structures.
- Rows 13051–13550 reinforce stabilization/recurrence with long delayed
  windows, decimal windows, full-temporal antecedents, whole-negated
  antecedents, event targets, event-absence targets, sustained negated
  state/range targets, and combinations such as
  `always(eventually[...](...))`,
  `always[...](eventually[...](...))`, `eventually(always[...](...))`,
  and `eventually[...](always(...))`.
- Rows 13051–13550 reinforce invariance/reachability and immediate responses
  with bounded and unbounded invariance, delayed reachability, same-instant
  event/state mixtures, mode predicates, open/closed ranges, event absence,
  and negated state or range requirements.
- Rows 13551–14050 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace and no confidence placeholders.
- Rows 13551–14050 add complete-formula modifiers over temporal
  subexpressions, including fall(historically(...)),
  fall(historically[...](...)), fall(once(...)), fall(always(...)),
  fall(eventually[...](...)), rise(always(...)), rise(always[...](...)),
  not rise(historically(...)), not rise(historically[...](...)),
  not rise(since(...)), not rise(until(...)),
  not fall(always[...](...)), and not fall(once[...](...)).
- Rows 13551–14050 expand whole-negated temporal responses and triggers over
  `always`, `always[...]`, `eventually`, `eventually[...]`,
  `historically[...]`, `once`, `since`, `since[...]`, `until`, and
  `until[...]`; scope is preserved over the complete temporal formula.
- Rows 13551–14050 reinforce cross-time pairings where full past, future, and
  binary temporal formulas serve as triggers or consequents for past
  responses, future responses, binary-temporal responses, and recurrence
  structures.
- Rows 13551–14050 reinforce stabilization/recurrence with long delayed
  windows, decimal windows, past-temporal antecedents, binary-temporal
  antecedents, whole-negated antecedents, event targets, event-absence
  targets, sustained negated state/range targets, and combinations such as
  `always(eventually[...](...))`,
  `always[...](eventually[...](...))`, `eventually(always[...](...))`,
  and `eventually[...](always(...))`.
- Rows 13551–14050 reinforce invariance/reachability and immediate responses
  with bounded and unbounded invariance, delayed reachability, same-instant
  event/state mixtures, mode predicates, open/closed ranges, event absence,
  and negated state or range requirements.
- Rows 14051–14318 complete the train split. This split-end batch is smaller
  than 500 rows because no train rows remain after row 14318.
- Rows 14051–14318 add complete-formula modifiers over temporal
  subexpressions, including rise(always[...](...)), rise(until(...)),
  rise(once[...](...)), fall(always[...](...)), fall(until[...](...)),
  fall(since[...](...)), not rise(eventually[...](...)),
  not rise(once[...](...)), not fall(eventually[...](...)), and
  not fall(since[...](...)).
- Rows 14051–14318 expand whole-negated temporal responses and triggers over
  `historically[...]`, `once[...]`, `eventually[...]`, `always`,
  `always[...]`, `until`, and `until[...]`; scope is preserved over the
  complete temporal formula.
- Rows 14051–14318 reinforce cross-time pairings where full past, future, and
  binary temporal formulas serve as triggers or consequents for past
  responses, future responses, binary-temporal responses, and recurrence
  structures.
- Rows 14051–14318 reinforce stabilization/recurrence with long delayed
  windows, decimal windows, past-temporal antecedents, binary-temporal
  antecedents, whole-negated antecedents, event targets, event-absence
  targets, sustained negated state/range targets, and combinations such as
  `always(eventually[...](...))`,
  `always[...](eventually[...](...))`, `eventually(always[...](...))`,
  and `eventually[...](always[...](...))`.
- Rows 14051–14318 reinforce invariance/reachability and immediate responses
  with bounded and unbounded invariance, delayed reachability, same-instant
  event/state mixtures, mode predicates, open/closed ranges, event absence,
  and negated state or range requirements.
- Test rows 1–500 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace and no extra numeric bookkeeping.
- Test rows 1–500 stay within the same four template families:
  invariance/reachability, immediate response, temporal response, and
  stabilization/recurrence.
- Test rows 1–500 reinforce complete-formula modifiers and whole temporal
  negation, including rise(always(...)), fall(always[...](...)),
  not rise(eventually(...)), rise(once[...](...)), fall(once(...)),
  fall(since(...)), not(eventually[...](...)), not(always[...](...)),
  not(since[...](...)), and not(until[...](...)).
- Test rows 1–500 reinforce cross-time pairings where `once`, `once[...]`,
  `historically`, `historically[...]`, `since`, `since[...]`, `until`,
  `until[...]`, `always`, `always[...]`, `eventually`, and
  `eventually[...]` serve as triggers, consequents, or recurrence conditions.
- Test rows 1–500 reinforce stabilization/recurrence with delayed, decimal,
  long, and nonzero windows, including `always(eventually(...))`,
  `always(eventually[...](...))`, `always[...](eventually(...))`,
  `always[...](eventually[...](...))`, `eventually(always(...))`,
  `eventually(always[...](...))`, and
  `eventually[...](always[...](...))`.
- Test rows 1–500 reinforce invariance/reachability and immediate responses
  with mixed state, mode, range, event, event-absence, whole-negated, and
  same-instant Boolean requirements.
- Test rows 501–1000 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace and no extra numeric bookkeeping.
- Test rows 501–1000 stay within the same four template families:
  invariance/reachability, immediate response, temporal response, and
  stabilization/recurrence.
- Test rows 501–1000 reinforce complete-formula modifiers over temporal
  inputs, including not rise(eventually[...](...)),
  not fall(eventually[...](...)), rise(until(...)), rise(until[...](...)),
  fall(until[...](...)), fall(always[...](...)), fall(once(...)), and
  not rise(since[...](...)).
- Test rows 501–1000 reinforce whole-negated temporal formulas over
  `eventually`, `eventually[...]`, `always`, `always[...]`, `since`,
  `since[...]`, `until`, and `until[...]`; negation scope stays attached to
  the full temporal expression.
- Test rows 501–1000 reinforce cross-time response pairings where `once`,
  `once[...]`, `historically`, `historically[...]`, `since`, `since[...]`,
  `until`, `until[...]`, `eventually`, and `eventually[...]` appear as
  antecedents or consequents.
- Test rows 501–1000 reinforce stabilization/recurrence with past, future,
  and binary-temporal antecedents; inner targets may be state, mode, range,
  event, event absence, or whole-negated requirements across short, long,
  decimal, delayed, and nonzero windows.
- Test rows 1001–1500 were processed as one 500-row batch. The update stays
  compact and semantic-only: no row trace and no extra numeric bookkeeping.
- Test rows 1001–1500 stay within the same four template families:
  invariance/reachability, immediate response, temporal response, and
  stabilization/recurrence.
- Test rows 1001–1500 reinforce complete-formula modifiers over temporal
  inputs, including not fall(until[...](...)), not fall(eventually(...)),
  fall(historically(...)), fall(always[...](...)), fall(once(...)),
  not rise(since[...](...)), and rise(until[...](...)).
- Test rows 1001–1500 reinforce whole-negated temporal formulas over
  `always`, `always[...]`, `eventually`, `eventually[...]`,
  `historically[...]`, `once[...]`, `since`, `since[...]`, `until`, and
  `until[...]`; negation scope stays attached to the full temporal expression.
- Test rows 1001–1500 reinforce cross-time pairings where past, future, and
  binary temporal formulas appear as antecedents or consequents.
- Test rows 1001–1500 reinforce stabilization/recurrence where inner targets
  may be state, mode, range, event, event absence, not-rise, not-fall, or
  whole-negated requirements across delayed, decimal, long, and nonzero
  windows.
- Test rows 1501–2000 were processed as one 500-row batch and complete the
  test split. The update stays compact and semantic-only: no row trace and no
  extra numeric bookkeeping.
- Test rows 1501–2000 stay within the same four template families:
  invariance/reachability, immediate response, temporal response, and
  stabilization/recurrence.
- Test rows 1501–2000 reinforce complete-formula modifiers over temporal
  inputs, including fall(once(...)), fall(historically(...)),
  fall(eventually[...](...)), fall(until[...](...)),
  not fall(always[...](...)), not fall(since(...)),
  not rise(eventually[...](...)), and not rise(until[...](...)).
- Test rows 1501–2000 reinforce whole-negated temporal formulas over
  `always`, `always[...]`, `eventually`, `eventually[...]`, `historically`,
  `historically[...]`, `once`, `once[...]`, `since`, `since[...]`, `until`,
  and `until[...]`; full-expression scope remains preserved.
- Test rows 1501–2000 reinforce cross-time pairings such as
  eventually-to-until, until-to-until, until-to-since,
  since-to-historically, since-to-until, since-to-recurrence,
  historically-to-until, and historically-to-recurrence.
- Test rows 1501–2000 reinforce stabilization/recurrence with future, past,
  binary-temporal, and whole-negated antecedents; inner targets may be state,
  mode, range, event, event absence, not-rise, not-fall, or whole-negated
  requirements across delayed, decimal, long, and nonzero windows.
