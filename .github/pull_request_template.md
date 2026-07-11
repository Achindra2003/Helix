## What this changes

A short description of the change and why.

## Scope

- [ ] This PR is scoped to one surface (a feature, a fix, or a doc pass)
- [ ] If it touches an `AI-LANE-CONTRACTS.md` interface (event kinds,
      endpoints, config), the doc is updated in this same PR

## Verification

- [ ] `cd backend && ./.venv/Scripts/python.exe -m pytest -q` passes
      (hermetic — paste the pass count)
- [ ] `cd frontend/app && npm run build` is clean (if frontend changed)
- [ ] Manually exercised the changed surface (describe how, or attach a
      screenshot/GIF for UI changes)

## Notes for reviewers

Anything a reviewer should know that isn't obvious from the diff — design
tradeoffs considered, things deliberately left out, follow-up issues filed.
