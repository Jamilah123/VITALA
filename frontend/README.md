# VITALA frontend

Arabic, right-to-left web app built with React, TypeScript, and Vite, from the
screens in `docs/Vitala_App_Screens.pdf`.

## Limitations

- **Synthetic data only.** The backend has no login, so anyone who can reach it can
  read every record. The dev server stays on `127.0.0.1`.
- **No clinical logic.** Screens other than the profile and medications show fixed
  demo content. Nothing is calculated from a profile.
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
| من الخادم | Date of birth, sex, diabetes and hypertension status, medications | Backend API | `src/api` |
| في هذا المتصفح فقط | Height, weight, lipid history, family history. The API has no fields for them yet | `localStorage` | `src/lib/session.tsx` |
| بيانات تجريبية | Everything about the persona "نورة": checks, results, activity, doctor view, chat, privacy settings | `src/demo/data.ts`, and demo actions in `localStorage` | `src/demo` |

Rules to keep when changing the code:

- `src/api` and `src/lib` never import from `src/demo`.
- A screen that shows demo data shows `DemoNotice`, or `SourceBadge` when it mixes
  sources. Demo actions never call the API.
- Unknown is not negative. A condition is `not_diagnosed` only if the user says so;
  otherwise it stays `unknown`.

## Screens

| PDF page | Screen | Path | Data |
|---|---|---|---|
| 1 | Welcome | `/welcome` | None |
| 1 | Open a profile by number (in place of login) | `/open-profile` | API |
| 2 | Basic information | `/onboarding/basic` | API and browser |
| 3 | Health history and medications | `/onboarding/history` | API and browser |
| 4 | Smart watch | `/onboarding/watch` | Demo |
| 5 | Finished | `/onboarding/done` | None |
| 6 | Home | `/home` | Demo |
| 7 | Checks | `/checks` | Demo |
| 8 | Check details | `/checks/:checkId` | Demo |
| 9 | Diabetes and blood pressure tracking | `/tracking` | Demo |
| 10 | Activity goal | `/activity` | Demo |
| 11 | Ask Vitala | `/chat` | Demo |
| 12 | Results log | `/log` | Demo |
| 13 | Doctor view | `/doctor` | Demo |
| 14 | Account | `/account` | API and demo |
| 14 | Health profile and medications | `/account/health` | API and browser |
| 14 | Sources | `/account/sources` | Demo |
