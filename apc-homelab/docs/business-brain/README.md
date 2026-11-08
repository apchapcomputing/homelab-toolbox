# Business Brain

Drafts for the vault that turn labelled Gmail newsletters into filtered, tagged notes feeding
Minimap Studio (what to build and test) and Faux Grad School (what to learn). Copy them into the
vault; Claude cannot write outside `Input/Clippings/`.

Flow: Gmail label `AI Ingestion` -> n8n `gmail-to-inbox` (every 15 min) -> `/srv/inputs` -> `brain-run`
-> Claude fills `summary`, tags, `idea-type`, `fgs`, `minimap`, `relevance`, `duplicate-of`
-> Dataview dashboard -> you promote ideas by hand.

| File | Goes to |
|---|---|
| `1-Input-CLAUDE-addition.md` | paste into the vault's `Input/CLAUDE.md` |
| `2-Business-Brain.md` | dashboard note (Dataview) |
| `3-Idea-Scorecard.md` | scoring template, 18 of 30 to proceed |
| `4-Business-Interest-Profile.md` | template; keep the real one private in the vault |

Rules of the design: Minimap startups are the FGS startups; FGS may also have learning projects
that earn nothing. Claude judges each newsletter item on its own, skips what the profile excludes,
and marks duplicates instead of re-surfacing them. An empty summary makes `brain-run` retry the note,
so skipped notes always get a one-line summary.
