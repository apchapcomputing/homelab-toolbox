---
tags:
  - 🗺️moc
  - business
  - dashboard
type: map
---
# Business Brain

Feeds [[Minimap Studio 💰]] (what to build and test) and Faux Grad School (what to learn and publish).

## Ideas awaiting validation
```dataview
TABLE summary AS "Summary", file.cday AS "Added"
FROM "Input/Clippings"
WHERE minimap = "candidate" AND relevance = "high" AND !contains(tags, "promoted") AND !duplicate-of
SORT file.cday DESC
```

## Strategies to test on a Minimap app
```dataview
TABLE summary AS "Summary", fgs AS "FGS goal"
FROM "Input/Clippings"
WHERE minimap = "test" OR idea-type = "strategy"
SORT file.cday DESC
```

## Risks and case studies
```dataview
TABLE summary AS "Summary", source AS "Source"
FROM "Input/Clippings"
WHERE minimap = "risk" OR idea-type = "case-study"
SORT file.cday DESC
```

## Market signals and pain points
```dataview
TABLE summary AS "Summary"
FROM "Input/Clippings"
WHERE idea-type = "market-signal"
SORT file.cday DESC
```

## By FGS goal
```dataview
TABLE length(rows) AS "Notes"
FROM "Input/Clippings"
WHERE fgs AND fgs != "none"
FLATTEN fgs AS goal
GROUP BY goal
```

## Minimap apps (these are the FGS startups)
```dataview
TABLE status AS "Status"
FROM "Projects/Minimap Studio 💰"
WHERE type = "saas-app"
SORT status ASC
```

## Unprocessed
```dataview
LIST
FROM "Input/Clippings"
WHERE !summary OR summary = ""
```

> Promote an idea: create `Projects/Minimap Studio 💰/<Name>.md` with `type: saas-app`, `status: idea`, fill in [[Idea Scorecard]], then add the tag `promoted` to the clipping.

## Filtered out (check Claude is not too strict)
```dataview
TABLE summary AS "Why"
FROM "Input/Clippings"
WHERE relevance = "skip" OR duplicate-of
SORT file.cday DESC
LIMIT 20
```
