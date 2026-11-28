# Schedule audit — whiteout-survival-data v0.11.0
Checked 2026-11-28 against all 65 original JSON files. All 65 imported; 50 contain structured schedule data, 28 contain structured repeat, 22 contain runs but no repeat, and 15 have no schedule object. The source does not establish actual local dates. The source registry remains pinned and original records are preserved.

## Complete classification (before supplements)
| Group | Count | Upstream event IDs |
|---|---:|---|
| fixed | 19 | `alliance-championship`, `alliance-showdown`, `armament-competition`, `bear-hunt`, `canyon-clash`, `defeat-nearby-beasts`, `foundry-battle`, `frostfire-mine`, `hall-of-chief`, `hall-of-heroes`, `heros-mission`, `icefire-warhymn-league`, `lucky-wheel`, `mercenary-prestige`, `officer-project`, `sunfire-castle`, `svs-state-of-power`, `tundra-trade-route`, `wild-brawl` |
| months | 8 | `alliance-mobilization`, `brothers-in-arms`, `fishing-tournament`, `king-of-icefield`, `mia-fortune`, `romance-season`, `snowbusters`, `tundra-trading-station-guide` |
| once | 1 | `beast-whisperer` |
| linked | 3 | `crazy-joe`, `crystal-reactivation-2`, `flame-and-fang` |
| irregular | 9 | `dreamscape-memory`, `frosty-fortune-skin-event`, `journey-of-light`, `shining-city-pack`, `silver-shell-events`, `state-merger`, `state-transfer-event`, `tundra-adventure`, `tundra-games` |
| conditions | 2 | `ginas-revenge`, `symphony-of-change` |
| persistent | 3 | `deadshot`, `the-labyrinth`, `tundra-album-2` |
| unknown | 20 | `city-development`, `develop-new-tech-2`, `develop-new-tech`, `frostdragon-tyrant`, `grow-your-heroes`, `hero-rally`, `home-beyond`, `plan-your-city`, `power-up`, `return-to-tundra`, `stand-of-arms`, `treasure-hunter`, `trial-event`, `trusted-chief`, `tundra-arms-league`, `tundra-star`, `vault-of-enigma`, `vision-of-dawn`, `war-preparation`, `working-overtime-2` |

## Changes
- Flame and Fang: source specifies Monday and Tuesday of SvS preparation, with a third trading day. Explicit state-level follow rule derives a three-day forecast from each actual scheduled preparation. A standalone four-week estimate is inherited from SvS only when the officer chooses independent dates. Changing or extending SvS automatically updates projections; cancelled parents produce cancelled forecasts.
- Crystal Reactivation: Friday and Saturday of the state-level Sunfire Castle week, derived from an explicitly enabled follow rule. Source does not establish a separate recurrence. No projection if Castle is not scheduled.
- Crazy Joe: Tuesday and Thursday of SvS, King of Icefield or Hall of Chief weeks; the alliance chooses the time and eligible local rotation. Keep the 40-minute duration and source relation, not a fabricated every-week repeat.
- Alliance Showdown, Brothers in Arms, Alliance Mobilization and King of Icefield require local rotation/eligibility review. Monthly rules are available as explicitly anchored calendar-month estimates, not fixed 30-day periods; monthly series are finite.
- Hall of Chief: explicit Season 1 or 2 selects six/seven-day duration. Frostfire Mine: actual slot selector with 30-minute duration and daily recurrence for the chosen slot. Icefire Warhymn League: full week includes Sunday preview and six-day competition.
- All other explicit repeat rules are retained; missing, irregular, generation-linked and ongoing schedules are displayed as such and require manual input where relevant. No dates are invented for these events. Multiple Frostfire Mine slots can be scheduled separately; choosing one does not schedule the other six.

## Safety and scope
Follow rules are explicitly enabled per group/state. They project read-only calendar items from local parent occurrences, not independent DB rows or results. Existing manual/cancelled dates take priority; an active independent rolling series prevents enabling follow mode. An active follow rule prevents creating a competing manual schedule. Stopping a rule retains past and already-started projections; new future dates stop. All derived entries remain estimated, including when a parent date is confirmed. Date moves in the parent calendar update dependent dates. No external API or provider added. Migration 0023 is additive. No automatic follow is introduced for uncertain Crazy Joe, Showdown or Brothers in Arms rotations; no legacy migration/enrollment.

## SvS full cycle
The upstream structured runs omit Matchmaking and Field Triage. The reviewed supplement adds Saturday/Sunday matchmaking (official FAQ), Preparation Monday 00:00 through Saturday 10:00, Battle Saturday 10:00–22:00, and an estimated Field Triage end on Tuesday 00:00 UTC (approximately 50 hours, community guide). The editor anchors on the Preparation Monday; all four phases are linked, projected at the same 28-day cadence, and can be reviewed and moved together. Flame and Fang follows Preparation specifically, not the earlier Matchmaking. Existing two-phase schedules are preserved and not silently rewritten; new cycles use all four phases. No additional event-picker choices or activity metrics are introduced.
