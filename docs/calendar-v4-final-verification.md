# Calendar v4 verification
Review baseline: main 0db8bbbb00342290cabf197d601ed657d3848c90 (PR 78, all six pre-merge jobs passed). Browser projects cover 1440, 1280 and 390 px. The final review addresses concrete gaps found in source inspection:
- A single phase edit must also reject overlapping other cycles, not only sibling phases.
- Phase start edits preserve existing duration; explicit precision changes can restore the appropriate phase reference. Future projected rows are validated independently, including unknown local battle time.
- Whole-cycle forms use page scrolling; review controls use one column. Browser smoke now exercises real creation and reconciliation on mobile as well as desktop, and asserts no horizontal overflow.
No external calendar integration or old schedule adoption is planned. No database or infrastructure change. Existing test coverage includes duplicate prevention, linked legions, grouping, revision checks, recurrence renewal and conflict handling; actual production usability and in-game state timings are still subject to officer verification.
