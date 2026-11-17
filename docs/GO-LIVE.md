# Going live: your checklist

About 30 minutes of your time, in four steps. Everything else is prepared.

**You never give me a password, a code or a token.** You log in yourself;
I only need the answers in the box below.

---

## What I need from you (just answers)

| # | Question | Example answer |
|---|---|---|
| 1 | ~~Whose name goes on the dataset?~~ Answered 2026-11-17: the project name, "Glasshouse". | |
| 2 | ~~Code public too?~~ Answered 2026-11-17: data and code. | |
| 3 | Your GitHub username, once you have one (step A). | `glasshouse-data` |
| 4 | The DOI Zenodo gives you (step C). | `10.5281/zenodo.1234567` |
| 5 | Your explicit "yes, publish" when I show you what will go public. | "yes, push the code" |

---

## Step A: create a GitHub account (5 min, only if the code goes public)

1. Go to https://github.com/signup and create a free account. If you chose "project name"
   in question 1, a username like `glasshouse-data` keeps your name off the page.
2. In GitHub: **Settings → Emails** → tick **"Keep my email addresses private"**.
   (This stops your personal email showing on public code.)
3. Tell me the username.

## Step B: log this computer into GitHub (2 min, only if the code goes public)

In the Terminal panel of this app, run:

```bash
gh auth login
```

Choose: **GitHub.com → HTTPS → Login with a web browser**. It shows a short code;
your browser opens; paste the code there and approve. Then tell me "logged in".

You do the login; I never see a password.

**Then I do the rest**, and stop before anything goes public:
- Replace the computer name in the project's history with your private GitHub address.
  Today every saved change shows your laptop's network name, which can reveal where you were.
- Run every check once more.
- Show you exactly what will become public.
- Push the code only after your "yes".

## Step C: put the data on Zenodo (10 min)

Zenodo is CERN's free research archive. It gives the dataset a permanent,
citable address (a DOI).

1. Go to https://zenodo.org → **Log in → with GitHub** (or with ORCID, or make
   a Zenodo account by email).
2. Click **New upload**.
3. Drag in the two files from this folder (open it in Finder:
   `glasshouse/data/releases/upload/`):
   - `glasshouse-v2026-11-17.zip` (660 MB, the whole dataset)
   - `MANIFEST.sha256` (lets anyone check the files are unchanged)
4. Fill in the form. You can copy and paste every value from the box below.
5. Click **Publish**. Copy the DOI it shows and send it to me. I put it into the
   README and citation file.

Prefer not to fill the form yourself? Say **"fill in Zenodo for me"**. I fill the
form in your browser and stop; you check it and click Publish.

| Zenodo field | Paste this |
|---|---|
| Resource type | Dataset |
| Title | Glasshouse — institutional accountability evidence dataset (say vs. do) |
| Creators | Glasshouse (type: Organization) |
| Description | the text below |
| Version | 2026-11-17 |
| License | Creative Commons Attribution 4.0 International |
| Keywords | proxy voting; SEC N-PX; asset managers; corporate governance; stewardship; shareholder voting; 13-F holdings; financial transparency; SEC EDGAR |

Description to paste:

> Glasshouse is a public, machine-readable record of what large asset managers say about
> how they vote their funds' shares (archived proxy-voting and stewardship policies, with
> dates) and how those funds actually voted (SEC Form N-PX), with 13-F holdings and a
> public enforcement record alongside.
>
> This version holds 9,684,226 fund vote lines from meetings between 1 July 2023 and
> 30 June 2026, filed by fund trusts of 16 financial institutions. For 13 of them
> (BlackRock, Vanguard, State Street, Fidelity, J.P. Morgan, Goldman Sachs, BNY, Invesco,
> T. Rowe Price, Franklin Templeton, DWS, Northern Trust, Charles Schwab) every kind of
> vote is on file for the fund trusts held. For UBS, BNP Paribas and Bank of America only
> executive-pay (say-on-pay) votes are on file. The fund trusts held are often a small
> part of a large manager, so this is not a complete record of any manager's voting. The
> dataset also holds 71 dated versions of 14 managers' policy documents (hashes, dates and
> archive links; no policy text), 580,106 13-F holding rows and 14,887 enforcement actions.
>
> Votes are attributed to the adviser that cast them, not the brand. Where one group's
> funds are voted by different advisers under different policies (BlackRock, Vanguard,
> T. Rowe Price, DWS), every vote carries an adviser_key, and a policy may only be
> compared with votes of the same key. Three derived tables give one row per manager per
> ballot item: shareholder proposals, director elections and say-on-pay. Every column
> and code is defined in DATASHEET.md, coverage and known gaps are in COVERAGE.json, and
> every file is checksummed in MANIFEST.sha256.
>
> The dataset records facts from public filings. It makes no finding of wrongdoing about
> anyone.

## Step D: done

**Completed 2026-11-17.** Data: https://doi.org/10.5281/zenodo.24321607 · Code: https://github.com/glasshouse-records/promises-kept-or-not

Once the DOI is in, I add it to the README and citation file. The dataset is then
public, citable and checkable. The next step, offering it to researchers,
journalists or organisations, is a separate decision I'll bring to you.

---

### Not needed

- Social media accounts. Posts about named companies are where the legal risk is.
  They should come from an organisation with legal cover, not from you personally.
- Paying for anything. GitHub and Zenodo are free for this.
