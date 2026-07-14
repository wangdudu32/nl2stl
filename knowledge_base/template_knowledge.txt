# The knowledge here is for reference only
# Compact STL Knowledge for Prompting

Use this as compact prompt knowledge for translating natural language into STL.
The key idea is to choose a structural template first, then fill temporal,
edge, and predicate slots. Do not map isolated trigger words to bare operators.

## Decision Order

1. Identify the top-level intent: invariance, reachability, response,
   stabilization, recurrence, or past-time condition.
2. Decide whether the top-level temporal operator is explicit or implicit.
   Conditional response language often implies an outer `always`.
3. Decide whether each temporal operator is bounded or unbounded.
4. Fill trigger/response/predicate slots.
5. Use `rise(...)` and `fall(...)` only with their operand structure.

## Top-Level Templates

### Invariance

- `always(<phi>)`
  Use when the sentence says the condition always holds globally or through the
  rest of the simulation. Cues: `always`, `globally`, `remain`, `keep`,
  `stay`, `continuously`, `consecutively`, `consistently`,
  `uninterruptedly`, `without interruption`, `all the time`,
  `in the future before the end`.
  Also treat `till/until the simulation ends`, `till/until the execution ends`,
  `till/until the end`, and `through the end` as unbounded future cues.

- `always [<t1>:<t2>] (<phi>)`
  Use when the condition must hold at every time point in an explicit interval.
  Cues: `for each/every time point`, `for each/every moment`,
  `for each/every time instant`, `during`, `within the first`, `in the next`,
  `coming`, `subsequent`, `following`.

### Reachability

- `eventually(<phi>)`
  Use when the condition must hold at some future time, with no explicit
  interval. Cues: `eventually`, `finally`, `ultimately`,
  `there exists a time`, `at some time before the end`.

- `eventually [<t1>:<t2>] (<phi>)`
  Use when the condition must hold at some time inside an explicit interval.
  Cues: `within <t1> to <t2>`, `in the next <t1> to <t2>`,
  `at a certain time during`, `after at most <t>`, `starting at most <t>`,
  `in less than <t>`, `coming`, `subsequent`, `following`.

### Conditional Response

- `always(<trigger> -> <response>)`
  Use for global conditional response. The outer `always` is often implicit.
  Cues: `if`, `when`, `whenever`, `everytime when`, `in case`,
  `on condition that`, `as soon as`, `while`, `during the interval that`,
  `in the event that`, `then`, `in response`.

- `always(<trigger> -> eventually [<t1>:<t2>] (<response>))`
  Use when a trigger requires a response sometime in a future interval.
  Cues: `then eventually`, `in response ultimately`, `within the next ...`.

- `always(<trigger> -> always [<t1>:<t2>] (<response>))`
  Use when a trigger requires the response to hold continuously throughout a
  future interval. Cues: `then for each time point`, `then continuously for`.

- `always(<trigger> -> eventually [<t1>:<t2>] (always [<t3>:<t4>] (<response>)))`
  Use for stabilization: after a trigger, eventually reach a state and then
  keep it for a duration. Cues: `there exists a time ... after which ... holds
  continuously`.

- `always(<trigger> -> always [<t1>:<t2>] (eventually [<t3>:<t4>] (<response>)))`
  Use for recurrence: throughout a future window, the response must repeatedly
  occur. Cues: `for every time point ... there exists a time ...`.

- `always(<trigger> -> (<left>) until [<t1>:<t2>] (<right>))`
  Use when after a trigger, `<left>` must hold until `<right>` happens in the
  future interval. Cues: `until`, `till then`, `before this`.

### Past-Time Conditions

- `historically(<phi>)` or `historically [<t1>:<t2>] (<phi>)`
  Use when the condition has held continuously in the past.
  Cues: `has always remained`, `has been keeping`, `in the past`, `last`,
  `elapsed`.

- `once(<phi>)` or `once [<t1>:<t2>] (<phi>)`
  Use when the condition occurred at least once in the past.
  Cues: `once`, `there existed a time in the past`, `at some time during the
  last ...`.

- `(<left>) since [<t1>:<t2>] (<right>)`
  Use when `<left>` has held continuously since a past occurrence of `<right>`.
  Cues: `since`, `after this`, `has been sustaining since`.

## Temporal Operators

- `always(<phi>)`: unbounded/default global or future invariance.
- `always [<t1>:<t2>] (<phi>)`: bounded invariance.
- `eventually(<phi>)`: unbounded future existence before the end.
- `eventually [<t1>:<t2>] (<phi>)`: bounded future existence.
- `historically(<phi>)`: unbounded past invariance since the beginning.
- `historically [<t1>:<t2>] (<phi>)`: bounded past invariance.
- `once(<phi>)`: unbounded past existence since the beginning.
- `once [<t1>:<t2>] (<phi>)`: bounded past existence.
- `(<phi>) until (<psi>)`: `<phi>` holds until `<psi>` eventually holds.
- `(<phi>) until [<t1>:<t2>] (<psi>)`: bounded future until.
- `(<phi>) since (<psi>)`: `<phi>` has held since past `<psi>`.
- `(<phi>) since [<t1>:<t2>] (<psi>)`: bounded past since.

## Formula-Level Negation

`not` can apply to a complete formula, not only to an atomic predicate.
Keep the full operand intact:

- `not(always [<t1>:<t2>] (<phi>))`: it is not true that `<phi>` holds
  throughout the interval.
- `not(eventually [<t1>:<t2>] (<phi>))`: there is no time in the interval
  where `<phi>` holds.
- `not(once [<t1>:<t2>] (<phi>))`: `<phi>` did not occur in the past interval.
- `not((<left>) since [<t1>:<t2>] (<right>))`: the whole since-condition is
  false; do not move `not` inside unless explicitly stated.
- `not((<left>) until [<t1>:<t2>] (<right>))`: the whole until-condition is
  false; do not move `not` inside unless explicitly stated.

Cues: `the following/subsequent condition is not true`, `will not be true`,
`the condition that ... is not true`, `it is not the case that ...`.

## Edge Operators

Interpret edge operators as transitions of the inner predicate:

- `rise(<phi>)`: `<phi>` changes from false to true.
- `fall(<phi>)`: `<phi>` changes from true to false.
- `not rise(<phi>)`: the false-to-true event is not observed.
- `not fall(<phi>)`: the true-to-false event is not observed.

Important: keep the operand structure.

Edge operators can apply to complete formulas as well as predicates:

- `rise(always(<phi>))`: the full always-condition changes from false to true.
- `rise((<left>) until [<t1>:<t2>] (<right>))`: the full until-condition changes
  from false to true.
- `fall(eventually [<t1>:<t2>] (<phi>))`: the full eventually-condition changes
  from true to false.

Cues: `the condition that ... shifts from false to true`, `changes from false
to true`, `is observed to shift from false to true` -> `rise(<full_formula>)`.
Cues: `changes from true to false`, `shall not change from true to false` ->
`fall(<full_formula>)` or `not fall(<full_formula>)`.

### Entering a Range

- NL: `<sig> enters [<lo>, <hi>]`, `<sig> gets into the range`,
  `<sig> settles inside the bound`, `<sig> enters the region`
- STL: `rise(<sig> >= <lo> and <sig> <= <hi>)`

Bracket variants:

- `[lo, hi]` -> `rise(<sig> >= <lo> and <sig> <= <hi>)`
- `(lo, hi)` -> `rise(<sig> > <lo> and <sig> < <hi>)`
- `(lo, hi]` -> `rise(<sig> > <lo> and <sig> <= <hi>)`
- `[lo, hi)` -> `rise(<sig> >= <lo> and <sig> < <hi>)`

### Leaving a Range

- NL: `<sig> leaves [<lo>, <hi>]`, `<sig> gets out of the range`,
  `<sig> deviates from [<lo>, <hi>]`, `<sig> leaves the range`,
  `<sig> goes out of the bound`
- STL: `fall(<sig> >= <lo> and <sig> <= <hi>)`

Bracket variants follow the same operand predicate as entering a range.
Do not summarize `deviates from` as bare `fall`; it is usually
`fall(<range_predicate>)`.

### Static Range Membership

- NL: `<sig> is in [<lo>, <hi>]`, `<sig> is within the range [<lo>, <hi>]`,
  `<sig> is in the closed interval [<lo>, <hi>]`
- STL: `<sig> >= <lo> and <sig> <= <hi>`

- NL: `<sig> is in the open interval (<lo>, <hi>)`
- STL: `<sig> > <lo> and <sig> < <hi>`

- NL: `<sig> is out of [<lo>, <hi>]`, `<sig> is outside of the range`,
  `<sig> is in the outside of the range`
- STL: `not (<sig> >= <lo> and <sig> <= <hi>)`

Use static range predicates when the sentence describes a state that holds now
or throughout an interval. Use `rise(...)`/`fall(...)` only when it describes an
entry or leaving transition/event.

### Equality Transitions

- NL: `<sig> becomes equal to <value>`, `<sig> gets set to <value>`,
  `<sig> settles to <value>`, `<sig> changes to <value>`,
  `<sig> gets changed to <value>`, `<sig> is changed to <value>`
- STL: `rise(<sig> == <value>)`

- NL: `<sig> starts not equaling <value>`, `<sig> starts deviating from
  <value>`, `<sig> leaves <value>`, `<sig> becomes not set to <value>`
- STL: `fall(<sig> == <value>)`

- NL: mode/state of `<sig1>` shifts to `<sig2>` or becomes `<sig2>`
- STL: `rise(<sig> == <sig>)`

- NL: mode/state of `<sig1>` deviates from `<sig2>` or leaves `<sig2>`
- STL: `fall(<sig> == <sig>)`

### Threshold Transitions

- NL: `<sig> becomes above <c>`, `rises above <c>`, `crosses <c>`,
  `<sig> becomes more/larger/higher than <c>`, `<sig> gets raised above <c>`
- STL: usually `rise(<sig> > <c>)`

- NL: `<sig> gets to at least/no less than <c>`, `<sig> jumps to no less than
  <c>`, `<sig> rises to greater than or equal to <c>`
- STL: `rise(<sig> >= <c>)`

- NL: `<sig> drops/falls/goes below <c>`, `<sig> goes lower than <c>`,
  `<sig> becomes lower than <c>`
- STL: usually `rise(<sig> < <c>)`

- NL: `<sig> gets to at most/no more than <c>`, `<sig> gets to no larger than
  <c>`, `<sig> becomes no larger than <c>`, `<sig> decreases to at most <c>`
- STL: `rise(<sig> <= <c>)`

- NL: `<sig> jumps/goes/rises/increases to <comparison>`,
  `<sig> falls/drops/decreases to <comparison>`
- STL: use `rise(<comparison_predicate>)` unless the sentence explicitly says a
  previously true threshold condition becomes false.

- NL: `<sig> decreases below <c>` when the previous condition was
  `<sig> >= <c>`
- STL: `fall(<sig> >= <c>)`

- NL: `<sig> increases above <c>` when the previous condition was
  `<sig> <= <c>`
- STL: `fall(<sig> <= <c>)`

## Predicate Patterns

- `equal to`, `equals to`, `set to`, `on`, `is in <sig2>`, `stay in <sig2>`,
  `keep in <sig2>` -> `<sig> == <value>` or `<sig> == <sig>`
- `greater than`, `above`, `higher than`, `bigger than`, `larger than`,
  `more than`, `over`, `exceeds` -> `<sig> > <c>`
- `at least`, `no less than`, `greater than or equal to`,
  `not less than <c>`, `not smaller than <c>` -> `<sig> >= <c>` or
  `not(<sig> < <c>)` when the STL explicitly uses negation.
- `less than`, `below`, `smaller than`, `lower than` -> `<sig> < <c>`
- `at most`, `no more than`, `no larger than`, `less than or equal to`,
  `not greater than <c>`, `not larger than <c>` -> `<sig> <= <c>` or
  `not(<sig> > <c>)` when the STL explicitly uses negation.
- `not less than or equal to <c>` -> `not(<sig> <= <c>)`.
- `not greater than or equal to <c>` -> `not(<sig> >= <c>)`.
- If the English explicitly negates a comparison phrase, keep the negation
  scope around that comparison unless the target STL clearly simplifies it.
- `not <predicate>` -> `not(<predicate>)`
- `all of the following`, `and` -> `<phi> and <psi>`
- `or`, `one of the following` -> `<phi> or <psi>`

Range predicates:

- `[lo, hi]` -> `<sig> >= <lo> and <sig> <= <hi>`
- `(lo, hi)` -> `<sig> > <lo> and <sig> < <hi>`
- `(lo, hi]` -> `<sig> > <lo> and <sig> <= <hi>`
- `[lo, hi)` -> `<sig> >= <lo> and <sig> < <hi>`

## Default Rules

- If a sentence has `if/when/whenever ... then ...`, add an outer
  `always(... -> ...)` unless a different top-level scope is explicit.
- If a sentence says `instantly`, `immediately`, `at once`, or `at the same
  time`, do not add `eventually` to the response solely because of the response.
- Immediate cues also include `without any delay`, `in no time`, `right away`,
  `promptly`, `simultaneously`, `same moment`, `same time point`, and
  `same time instant`.
- If a sentence says `within/next/following/coming/subsequent <interval>` and
  asks for existence, use `eventually [<t1>:<t2>]`.
- If a sentence says `after at most <t>`, `starting at most <t>`, or `in less
  than <t>` and asks for existence, use `eventually [0:<t>]`.
- If a sentence says `for each/every time point/moment within <interval>`, use
  `always [<t1>:<t2>]`.
- If no explicit time interval is present, use the unbounded/default form:
  `always(<phi>)`, `eventually(<phi>)`, `historically(<phi>)`, or `once(<phi>)`.
- Past phrases should use `historically`, `once`, or `since`; future phrases
  should use `always`, `eventually`, or `until`.

## Worked Examples

- NL: `<sig> deviates from [<lo>, <hi>]`
  STL structure: `fall(<sig> >= <lo> and <sig> <= <hi>)`

- NL: `<sig> is out of the range [<lo>, <hi>]`
  STL structure: `not (<sig> >= <lo> and <sig> <= <hi>)`

- NL: `whenever <trigger>, <response> happens within the next <t1> to <t2>`
  STL structure: `always(<trigger> -> eventually [<t1>:<t2>] (<response>))`

- NL: `whenever <trigger>, <response> happens without any delay`
  STL structure: `always(<trigger> -> <response>)`

- NL: `for each time point in the next <t1> to <t2>, <phi>`
  STL structure: `always [<t1>:<t2>] (<phi>)`

- NL: `there exists a time in the past <t1> to <t2> where <phi>`
  STL structure: `once [<t1>:<t2>] (<phi>)`

- NL: `<left> holds until <right> happens within <t1> to <t2>`
  STL structure: `(<left>) until [<t1>:<t2>] (<right>)`

- NL: `the condition that <left> holds until <right> shifts from false to true`
  STL structure: `rise((<left>) until (<right>))`

- NL: `the subsequent condition is not true: <phi>`
  STL structure: `not(<phi>)`
