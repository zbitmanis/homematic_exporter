# Specs

Artifact chain: `intent/*.intent.md` → `specs/spec.md` → `specs/plan.md` → PR. Commit each before the next stage starts.

## spec.md (generated from the accepted intent, reviewed by the owner)
Headings: Summary · Requirements (numbered, testable) · Module interfaces (mirror `docs/sbom/components.md`) · Metric catalogue (name, type, unit, labels, source field) · Config (env var, default) · Flagged concerns · Open questions resolved/carried forward.

Prompt: "Document the spec fully as spec.md, ready to hand to the engineering team. Describe clearly any areas of concern, especially where you cannot satisfy contradicting policies."

First Design task: a spike against a real access point to close the intent's open questions 1, 2, 3 and 5.

## plan.md (one per task, committed after plan mode)
Headings: Files that change · Order of work · Risks · Proof. Bar: an engineer who has never seen the conversation can implement from it alone.
