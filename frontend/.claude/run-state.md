# Run State — VinUni Overnight Burst

## Batch 1 DONE — CV AI Wire-Up + Scheduler Startup
- Added `getSuggestion`, `requestAiSuggestion`, `acceptAiSuggestion`, `rejectAiSuggestion` + types to `frontend/src/lib/api/cv.ts`
- Rewrote `cv-ai-assist-card.tsx` with real idle → requesting → processing → diff → accept/reject flow
- Wired `cvId` + `sections` into `cv-builder-screen.tsx` line 611
- Added AI i18n keys to vi.json + en.json (requesting/processing/diffTitle/before/after/factConfirm/accept/reject/failed)
- Fixed `backend/app/bootstrap/lifespan.py` — starts `runner.run_forever()` as asyncio background task when `BACKGROUND_WORKER_MODE=scheduler`
- Checks: `npx tsc --noEmit` clean, `uv run python -c "from app.bootstrap.lifespan import lifespan"` → OK

## Current Batch: BATCH-2 — Student Navigation IA Rescue

### Goal
Student currently uses a sidebar workspace layout. The product spec requires a
public marketplace top-navigation (logo, search, nav links, auth/avatar). The
sidebar workspace should only appear inside authenticated student workspace
screens, not wrapping the entire public-facing student experience.

### Confirmed Gaps (need to verify code)
- Check `frontend/src/components/layout/` for student nav shell
- Check `frontend/src/app/` routing for student pages
- Spec: public discovery pages → top-nav with search; workspace pages → sidebar

### Slices
1. Read current layout shell for student-facing pages
2. Compare against spec requirements
3. Fix nav shell or add correct top-nav wrapper

### Files Expected to Change
- Layout shell components in `frontend/src/components/layout/`
- Student page layouts in `frontend/src/app/`

### Cheap Checks
- `npx tsc --noEmit`
- Visual inspect of nav structure in code

### Glass Token Reference
- Card: `border border-white/60 bg-white/82 backdrop-blur-md shadow-[0_2px_12px_rgba(11,34,57,0.06)]`
- Info panel: `border border-white/60 bg-white/72 backdrop-blur-sm`
- Dashed: `border-dashed border-white/50 bg-white/60`

### Next Batches
- BATCH-3: Homepage hero image (vinuni-campus.png wired)
- BATCH-4: Discovery/recommendation labels (recent vs recommended honesty)
