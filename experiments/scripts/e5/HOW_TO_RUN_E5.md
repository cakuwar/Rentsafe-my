# E5: how to run it

E5 measures how long RentSafe takes per chat and how it copes with 10 people at once. It runs on a **separate copy** of the system, so your demo database and Redis are never stopped, restarted or written to.

## Before you start
1. Keep only **Docker Desktop** and **VS Code** open. Close Chrome (including its tray icon), games, Teams and other apps.
2. Have your keys ready: `OPENAI_API_KEY`, `SERPER_API_KEY` and `GEMINI_API_KEY`, the same ones as in `backend\.env`. The script asks for each one, and what you paste is hidden.
3. Plan for about 15–20 minutes. Don't use the laptop for anything else while it runs, because that would slow down the timings.

## Run
Open a PowerShell terminal in the repo folder and type:

```
powershell -NoProfile -ExecutionPolicy Bypass -File experiments\scripts\e5\RUN_E5.ps1
```

Paste each key when asked, then press Enter. If you leave a key empty, that part is switched off.

## What it does
1. **Pre-flight:** records git status, HEAD, the hashes of the model and price-baseline files, and your demo containers.
2. **Copy:** copies the code (without any `.env` file) and the model weights to `~\rentsafe_experiments_data\e5_stack`.
3. **Separate stack:** starts its own PostgreSQL (port 5433) and Redis (port 6380) as Docker project `rentsafe_exp`, then loads the price baseline and the lexicon into it.
4. **Test A:** runs the 15 blind cases once each, one at a time, with an empty cache. It times each stage and checks every score against Table 4.11.
5. **Test B:**
   - 10 users for 3 minutes on the text endpoint;
   - a shorter run from one shared address, to show the rate limit;
   - 10 screenshot requests at the same time.

   Test B uses no agent details, and the search and Gemini keys are withheld, so it spends no search credits.
6. **Teardown:** removes **only** `rentsafe_exp`.
7. **Post-flight:** checks that everything recorded in step 1 is unchanged.

## Cost
At most about **725** gpt-4o-mini explanation calls, which is under about **US$0.40**. On top of that:
- up to **14** Serper searches from your free credits;
- up to **26** Gemini judge calls.

The real number of calls depends on how fast the laptop is.

## Repeating Test A only

Use this if, for example, a key was wrong. It does the same set-up, Test A and teardown, and skips Test B:

```
powershell -NoProfile -ExecutionPolicy Bypass -File experiments\scripts\e5\RUN_E5.ps1 -OnlyA
```

## Afterwards
Tell Claude "E5 done".
- Results without chat text are saved in `experiments\results\e5\<time>\`.
- Logs and full responses are saved in `~\rentsafe_experiments_data\e5\<time>\`, outside the repo.
