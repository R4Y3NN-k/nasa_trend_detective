# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Layered audiences, shown in this order of depth (each layer needs the one before it, not the one after):
1. Students: first contact, learning what a trend and a significance test are.
2. Farmers: whether rain, heat or soil wetness are changing where they farm, in plain words.
3. Firms and companies: whether a region's change is solid enough to plan around, with the cross-checks.
4. Researchers: the full method, the zone tree, the test values and the downloads.

## Product Purpose
Trend Detective answers "is this Earth variable really changing in this region?" It fetches 1981 to 2025 monthly NASA data for a box, removes the seasons, and reports the rate per decade with a 95% interval, a t-test and a Mann-Kendall test, then a verdict. Success: a first-time user reaches a verdict in two clicks, and an expert can drill from the whole region to a single governorate.

## Positioning
It is the only tool that combines a tested verdict, opposite-trend zones inside one region (a zone tree and map), and independent NASA cross-checks for every variable, all from NASA's own data with no login needed for the main path.

## Operating Context
Used live in a demo (2 to 3 minutes for judges), on a laptop browser, and by people who may be on a phone in the field, so it must work at phone width.

## Capabilities and Constraints
- Main data: NASA POWER (MERRA-2) for temperature, rain and topsoil wetness, 1981 to 2025. Cross-checks: GPM IMERG, CHIRPS, AIRS, GLDAS, FLDAS via Giovanni (needs an Earthdata login; the app must still work without one), and MODIS/VIIRS NDVI via AppEEARS.
- Existing front end: a single page (web/static/index.html, app.css, app.js) with a hand-written stylesheet (no Tailwind, no build step), Leaflet for the map and Plotly for charts, served by a standard-library Python server. The stack is decided and is not part of this record.
- Two levels of detail, Simple (default) and Expert, switched in the panel header. Both show the same verdict and numbers; Expert only adds depth (principle 2). Decided 15 Nov 2026.
- Colour roles: teal for actions and brand; orange and blue only for direction (rising, falling); amber only for real caution (datasets disagree, all-sea selection). Icons are one inline-SVG set, never emoji.
- Place search uses a list bundled with the app (demo areas, capitals, large cities), not a third-party geocoder.
- Terminology: "trend per decade", "95% range", "significant" (both tests p < 0.05 and the same sign), "suggestive" (either p < 0.10), "single source only". Say "consistent with", never "caused by".
- Undecided: the name and wording of the cross-check summary ("3 NASA sources agree") are proposals from the plan, not yet tested with users.

## Brand Commitments
The product is called "Trend Detective". Its voice is plain and direct, and it admits uncertainty. No NASA logos, flags or mission identifiers appear anywhere. Every AI-assisted part carries the SI disclosure.

## Evidence on Hand
Real NASA results for Tunisia, Northern Tunisia, governorates, Nile Delta, Western Sahel, Luanda and Namibe (see docs/demo_stories.md). A hand check of the Tunisia temperature trend (docs/validation.md). The calibration table in docs/validation.md is the honest coverage (92 to 95%, not an exact 95%). Do not invent testimonials, users or benchmarks.

## Product Principles
1. Show the evidence before the verdict; never a number the app did not compute from real data.
2. Each layer adds depth without hiding the layer before it: a student's answer is still the expert's answer.
3. Say what is not known: "no clear trend yet" and "single source only" are full answers, not errors.
4. Opposite trends inside a region are the point, not an outlier to hide.

## Accessibility & Inclusion
Phone width must work (the plan asks for this). Colour is never the only signal: the zone map and tree also carry text labels, signs and significance dots. Keyboard focus must be visible.
