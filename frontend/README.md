# VITALA frontend

Arabic, right-to-left web app built with React, TypeScript, and Vite, from the
screens in `docs/Vitala_App_Screens.pdf`.

## Limitations

- **Synthetic data only.** The backend has no login, so anyone who can reach it can
  read every record. The dev server stays on `127.0.0.1`.
- **No approved clinical logic.** The checks screens show the backend's screening
  summary, built from draft rules that no clinician has reviewed. They are labelled
  as such, show no due dates or schedules, and never present a rule as a
  recommendation. Other screens marked as demo show fixed content.
- **The chat is not AI.** It shows fixed replies and says so. Typed text goes nowhere.

## Running it

You need [Node.js](https://nodejs.org) 22 or later. Start the backend first (see
`backend/README.md`), then run these from the `frontend` folder:

```powershell
npm install

# Start the app at http://127.0.0.1:5173/. Press Ctrl+C to stop it.
npm run dev

# Run the unit tests.
npm test

# Check types and build for production.
npm run build
```

The dev server forwards `/api/*` to `http://127.0.0.1:8000`, so the backend needs no
CORS settings. Set `VITALA_API_TARGET` to use another address.

## Where data comes from

Each kind of data is kept apart in the code and labelled on screen.

| Label | Data | Stored in | Code |
|---|---|---|---|
| من الخادم | Profile, risk factors, medications, screening summary and rules, screening history, rule sources | Backend API | `src/api` |
| في هذا المتصفح فقط | Height, weight, lipids, and family history typed before the API stored them. Kept as they are and offered once for import on the health profile page; never overwritten | `localStorage` | `src/lib/session.tsx`, `src/lib/riskProfile.ts` |
| بيانات تجريبية | The persona "نورة": diabetes and blood pressure tracking, activity, doctor view, chat, privacy settings | `src/demo/data.ts`, and demo actions in `localStorage` | `src/demo` |

Rules to keep when changing the code:

- `src/api` and `src/lib` never import from `src/demo`.
- A screen that shows demo data shows `DemoNotice`, or `SourceBadge` when it mixes
  sources. Demo actions never call the API.
- Unknown is not negative. A condition is `not_diagnosed` only if the user says so;
  otherwise it stays `unknown`.
- Screening codes are shown in Arabic through `src/lib/screening.ts`. An unknown code
  is shown as it is. No screen renders `schedule_text_ar`, a due date, or an overdue
  label, and the tests in `src/lib/screening.test.ts` check this.
- Completed tests (`recorded_tests`, green) are always shown apart from draft rules
  (blue "قد تنطبق", amber "تحتاج معلومات").
- UI text is formal Arabic: gender-neutral where possible, otherwise standard
  masculine. `src/lib/wording.test.ts` fails on common feminine-specific forms.
- Risk factors are shown and stored, but never interpreted. Only the existing BMI
  card shows a general adult category, labelled as not a diagnosis.

## Screens

| PDF page | Screen | Path | Data |
|---|---|---|---|
| 1 | Welcome | `/welcome` | None |
| 1 | Open a profile by number (in place of login) | `/open-profile` | API |
| 2 | Basic information | `/onboarding/basic` | API and browser |
| 3 | Health history and medications | `/onboarding/history` | API and browser |
| 4 | Smart watch | `/onboarding/watch` | Demo |
| 5 | Finished | `/onboarding/done` | None |
| 6 | Home | `/home` | API (screening summary) and demo (activity, chat) |
| 7 | Checks | `/checks` | API |
| 8 | Check details, history, and rules | `/checks/:testId` | API |
| 9 | Diabetes and blood pressure tracking | `/tracking` | Demo, with links to API check details |
| 10 | Activity goal | `/activity` | Demo |
| 11 | Ask Vitala | `/chat` | Demo |
| 12 | Screening history | `/log` | API |
| 13 | Doctor view | `/doctor` | Demo |
| 14 | Account | `/account` | API and demo |
| 14 | Health profile and medications | `/account/health` | API and browser |
| 14 | Rule sources | `/account/sources` | API |
