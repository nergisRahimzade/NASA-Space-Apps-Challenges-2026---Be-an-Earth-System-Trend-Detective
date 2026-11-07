# Earth System Trend Detective

A Python project for investigating changes in Earth system data using NASA datasets, statistical trend tests, charts, and a Streamlit dashboard. AI explanations are planned for the analysis results.

The current app is a starter page. Data downloads, trend analysis, and AI explanations are not wired up yet. You can launch it without a dataset, NASA credentials, or an API key.

## First-time setup

### 1. Install Git and uv

Install [Git](https://git-scm.com/downloads) if needed. We use [uv](https://docs.astral.sh/uv/getting-started/installation/) to manage Python and project dependencies.

**Windows PowerShell:**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS or Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Reopen your terminal after installation, including any terminal inside your editor. Check that both tools are available:

```text
git --version
uv --version
```

### 2. Clone the repository

On the GitHub repository page, select **Code** and copy the HTTPS clone URL. Replace `REPOSITORY_URL` below with that URL:

```text
git clone REPOSITORY_URL earth-system-trend
cd earth-system-trend
```

If you already cloned the repository, open a terminal in that folder and run `git pull` instead. Run the remaining commands from the project root, where `pyproject.toml` is located.

### 3. Install Python and dependencies

```text
uv python install 3.12
uv sync --locked
```

The project selects Python 3.12 through `.python-version`. Syncing creates a local `.venv` and installs the project, its scientific and dashboard packages, and development tools. MetPy and OpenAI are already declared dependencies and are included in this installation.

The `--locked` option checks that `uv.lock` matches `pyproject.toml` and uses the recorded versions. You do not need to run `uv init`, install packages individually, or activate the environment manually when using `uv run`. See the [uv syncing documentation](https://docs.astral.sh/uv/concepts/projects/sync/).

### 4. Create local working folders

Git does not track empty directories. The raw and processed data directories are also intentionally ignored. Run this command in PowerShell, macOS, or Linux to create the working folders without changing existing files:

```text
uv run --locked python -c "from pathlib import Path; folders = ['data/raw', 'data/processed', 'results/figures', 'notebooks', 'scripts', 'tests', 'evaluation', 'docs']; [Path(folder).mkdir(parents=True, exist_ok=True) for folder in folders]"
```

This creates directories only. It does not download NASA data or generate analysis results. Dataset-specific download and processing instructions will be added when those workflows are implemented.

### 5. Start the dashboard

```text
uv run --locked streamlit run app/streamlit_app.py
```

Open the local URL printed in the terminal, usually `http://localhost:8501`. You should see **Earth System Trend Detective** and a message about connecting saved results. Stop the app with **Ctrl+C**.

### 6. Start the API

The API serves analysis results to the dashboard. By default it serves the mock file `results.mock.json` from the project root; see `USE_MOCK` in step 7.

```text
uv run --locked uvicorn earth_system_trend.api:app --reload
```

Run this from the project root so the API can find `results.mock.json`. Then open:

- `http://localhost:8000/health` should return `{"status": "ok"}`. This checks that the server is running.
- `http://localhost:8000/results` returns the contents of `results.mock.json` (see `docs/contract.md`).
- `http://localhost:8000/series?region=Example%20Region` returns one monthly series (region, variable, units, period and the monthly values) for the chart. An optional `&variable=...` narrows it. A region or variable with no data returns 404.
- `http://localhost:8000/trend` returns just the trend numbers (slope, p-value, tau, direction) and the explanation, for the stat cards.
- `http://localhost:8000/regions` lists every region with data and its trend: the whole study area first, then each sub-region. Use a region's `id` in `/series?region=...` and `/trend?region=...`.
- `http://localhost:8000/docs` lists every endpoint and lets you try them.

`/results`, `/series` and `/trend` check the results file against `docs/contract.md` first. A missing file returns 404; a file that breaks the contract returns 500 with a message naming the bad field.

Stop the API with **Ctrl+C**. To serve a different results file, set the `RESULTS_PATH` environment variable before starting it.

### 7. Configure settings (optional)

Backend settings are read from environment variables by `src/earth_system_trend/config.py`. For local work, copy the example file and fill in what you need:

```text
cp .env.example .env
```

On Windows PowerShell, use `Copy-Item .env.example .env`. The `.env` file is git-ignored, so keys stay on your computer. On a server, set the same variables in the host's dashboard instead.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | not set | Enables AI explanations. Without it, a fallback summary is used. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for explanations. |
| `OPENAI_TIMEOUT_S` | `15` | Seconds to wait for the model before giving up. |
| `USE_MOCK` | `true` | `true` serves the fake `results.mock.json`; `false` serves the real `results/results.json` made by the pipeline. |
| `RESULTS_PATH` | not set | Serve this results file instead, whatever `USE_MOCK` says. |
| `SERIES_CSV_PATH` | `data/processed/timeseries.csv` | The Data layer's monthly `date,value` CSV that the pipeline reads. |
| `EXPLAIN_CACHE_PATH` | `data/cache/explanations.json` | Where explanations are cached. A repeat request with the same input reuses the saved answer instead of calling the API. Delete the file to clear the cache. |
| `LOG_LEVEL` | `INFO` | How much the API logs (`DEBUG`, `INFO`, `WARNING`). |
| `CORS_ORIGINS` | `http://localhost:8501` | Comma-separated web addresses whose pages may call the API from a browser. Add the deployed dashboard's address here. |
| `RATE_LIMIT_PER_MINUTE` | `60` | Requests each visitor may make per minute (`/health` is exempt). `0` turns the limit off. |
| `API_URL` | `http://localhost:8000` | Where the dashboard and `scripts/smoke_test.py` find the API. |

To check that a running API answers its main endpoints, run `uv run --locked python scripts/smoke_test.py`, or pass the deployed address: `uv run --locked python scripts/smoke_test.py https://<service-name>.onrender.com`.

### 8. Build results.json with one command

The pipeline reads the Data layer's monthly CSV (`data/processed/timeseries.csv`, columns `date,value`), runs the trend test, asks the AI for an explanation, checks everything against `docs/contract.md`, and saves `results/results.json`:

```text
uv run --locked python -m earth_system_trend.run
```

To build one results file per sub-region instead, run it with `--all-regions`. It reads the sub-region list in `docs/subregions.json` and each `data/processed/timeseries_<id>.csv`, and writes `results/regions/<id>.json`, which `/regions` serves when `USE_MOCK=false`.

Before real data exists, add `--stub` to write a fake CSV first and try the whole chain. The command skips the work if `results/results.json` is already newer than the CSV; add `--force` to rebuild. To serve the new file, set `USE_MOCK=false` (step 7) and restart the API.

### 9. Run the API in Docker and deploy it

The `Dockerfile` packages the API so it runs the same everywhere. With [Docker](https://docs.docker.com/get-started/get-docker/) installed:

```text
docker build -t esd-api .
docker run -p 8000:8000 --env-file .env esd-api
```

Then open `http://localhost:8000/health`. Leave out `--env-file .env` if you have no `.env` file.

To deploy on [Render](https://render.com/docs/docker): create a **Web Service** from this GitHub repository, choose **Docker** as the language, and add the environment variables from step 7 in the service's **Environment** settings, never in the repository. Render sets `PORT` itself. When the deploy finishes, open `https://<service-name>.onrender.com/health`; it should return `{"status": "ok"}`.
#### Using the live API

The team's API is deployed at **https://earthtrend.onrender.com**. This address is not a secret. To run the dashboard against it instead of a local API:

**Windows PowerShell:**
**or the vscode terminal powershell**
```text
$env:API_URL = "https://earthtrend.onrender.com"
uv run --locked streamlit run app/streamlit_app.py
```

**macOS or Linux:**

```text
API_URL=https://earthtrend.onrender.com uv run --locked streamlit run app/streamlit_app.py
```

The bottom of the page should say **Showing results from: API at https://earthtrend.onrender.com**. The API runs on Render's free tier and sleeps after 15 minutes without requests. If the page shows mock data or an error, wait about 30 seconds and refresh.

To check the live API directly: `uv run --locked python scripts/smoke_test.py https://earthtrend.onrender.com`
## NASA Earthdata access

This step is needed when working on data downloads, but is not required to launch the starter dashboard.

Each teammate downloading NASA data should create their own free [Earthdata Login account](https://urs.earthdata.nasa.gov/). To check interactive authentication, start Python:

```text
uv run --locked python
```

Then enter:

```python
import earthaccess
auth = earthaccess.login(strategy="interactive")
print(auth.authenticated)
exit()
```

Enter your own username and password when prompted. A successful authentication prints `True`. This check authenticates the current Python session; download scripts should also call `earthaccess.login()` when implemented. See the [earthaccess authentication guide](https://earthaccess.readthedocs.io/en/latest/user/explanation/authenticate/).

Keep credentials out of source code and Git. The existing `.gitignore` excludes `.env` files, `.netrc`, `_netrc`, and `.streamlit/secrets.toml`. Installing the OpenAI package does not configure AI access; set `OPENAI_API_KEY` in your `.env` file as described in step 7.

## Download a three-file sample (Day 4)

From the project root:

```text
uv run --locked python src/download.py --interactive
```

Log in once with Earthdata; the script then downloads three MOD11C3.061 monthly
files for January–March 2003 automatically. The Phoenix search window is fixed
at `(-112.4, 33.2, -111.6, 33.8)`. The original files are global, about 210 MB in
total. Nighttime measurements are selected during later processing.

Files go to `data/raw/day4_sample/`. The script checks the filenames, month count,
catalogue file sizes and HDF4 signatures, then writes sizes and checksums to
`data/day4_download_check.json`. Valid existing files are reused and reported
separately from new downloads.

If Earthdata credentials are already configured, omit `--interactive` to run
without prompts. Use `--start`, `--end`, `--count` and `--output` to change the
date window, file count or destination.

Three-file live check: [download record](docs/evidence/day4/download_check.json).

## Build the monthly series (Day 9)

After producing `data/processed/clean.nc` in [Day 8](https://github.com/nergisRahimzade/NASA-Space-Apps-Challenges-2026---Be-an-Earth-System-Trend-Detective/pull/19), run:

```sh
uv run --locked python -m earth_system_trend.aggregate
```

This writes `data/processed/timeseries.csv`: one nighttime LST value in °C per
month, using `cos(deg2rad(lat))` weights across Phoenix. The `date,value` columns
work with the existing backend reader. A month with no data keeps its date and
a blank value.

The small CSV is tracked; raw and cleaned datasets remain local. See
[monthly series notes](docs/monthly_series_notes.md) for the method and inherited
quality policy, and [the check record](docs/evidence/day9/series_check.json) for validation.

## Calculate monthly anomalies (Day 10)

```sh
uv run --locked python -m earth_system_trend.anomaly
```

This reads `data/processed/timeseries.csv` and subtracts the 2003-2024 mean for
each calendar month. It saves `data/processed/anomaly.csv` with the same
`date,value` columns, in °C differences.

The baseline means, counts and original-versus-anomaly plot are under
`docs/evidence/day10/`. See [anomaly notes](docs/anomaly_notes.md) for the
baseline definition and inherited quality policy.

## Build the subregion series (Day 11)

```sh
uv run --locked python -m earth_system_trend.subregions
```

This reads `data/processed/clean.nc` and the four boxes in `docs/subregions.json`,
then writes `timeseries_phoenix_northwest.csv`, `timeseries_phoenix_northeast.csv`,
`timeseries_phoenix_southwest.csv` and `timeseries_phoenix_southeast.csv` under
`data/processed/`. Each contains 264 `date,value` rows in °C.

The command checks coverage, overlapping cells, CSV readback and reconstruction
of the whole-window mean. See [subregion notes](docs/subregion_notes.md) for
bounds, the overview plot and the inherited quality policy. API registration
of the new regions is a later backend task.

## Check per-cell feasibility (Day 12)

```sh
uv run --locked python -m earth_system_trend.chunk_check
```

This chunks the nighttime data with `time=-1, lat=50, lon=50`, verifies a
centered 16-cell sample and times the existing trend function. The
[decision](docs/chunking_decision.md) and [check record](docs/evidence/day12/chunk_check.json)
record whether to try the optional per-cell map or retain the subregions.

## After pulling team changes

From the repository root, run:

```text
git pull
uv sync --locked
uv run --locked streamlit run app/streamlit_app.py
```

Sync after pulling so your local environment receives dependency updates. If working directories are missing, rerun step 4.

## Run the end-to-end test (Day 14)

```sh
uv run --locked python -m earth_system_trend.e2e            # committed CSVs, API in-process
uv run --locked python -m earth_system_trend.e2e --live     # same, through a real uvicorn server
uv run --locked python -m earth_system_trend.e2e --stub     # fake CSVs, no Data layer files needed
```

This runs the whole chain in a temporary folder: the pipeline builds
`results.json` and one file per sub-region, the API serves them with
`USE_MOCK=false`, and every endpoint's answer is checked against the contract
models in `src/earth_system_trend/contract.py`. It also checks that the API
serves exactly what the pipeline wrote, that each series has one entry per
month, that each trend label agrees with its p-value, and that an unknown
region answers 404. Your `results/` folder is not touched, and no OpenAI key
is used unless you add `--with-ai`. Add `--keep <folder>` to look at the files
afterwards. CI runs the `--live` version on every pull request and tag.

## Project structure

```text
earth-system-trend/
|-- app/streamlit_app.py       # Streamlit dashboard entry point
|-- src/earth_system_trend/   # Reusable Python package
|-- data/
|   |-- raw/                 # Original NASA files; ignored by Git
|   `-- processed/           # Cleaned datasets; ignored by Git
|-- results/
|   `-- figures/             # Saved charts and maps
|-- notebooks/               # Exploratory analysis
|-- scripts/                 # Future download and processing commands
|-- tests/                   # Automated tests as they are added
|-- evaluation/              # AI explanation test cases
|-- docs/                    # Dataset notes and methodology
|-- .python-version          # Selected Python version
|-- pyproject.toml           # Project metadata and dependencies
|-- uv.lock                  # Resolved dependency versions
`-- README.md
```

The planned workflow is: download files into `data/raw/`, save cleaned datasets in `data/processed/`, and write dashboard-ready tables and statistics into `results/`. The dashboard should read prepared results instead of processing raw satellite files on each interaction.

Small, intentional outputs such as `timeseries.csv` and `trend_results.json` can be committed for teammates to use. Large datasets belong outside Git. Cloning the repository does not supply ignored datasets.

## Adding dependencies

When a feature requires a new package, replace `PACKAGE_NAME` with its package name:

```text
uv add PACKAGE_NAME
```

For development-only tools, use `uv add --dev PACKAGE_NAME`. Commit both `pyproject.toml` and `uv.lock`. Teammates then install the change with `uv sync --locked` after pulling. See the [uv project guide](https://docs.astral.sh/uv/guides/projects/).

Keep `.venv/` local. Commit `.python-version` when intentionally changing the team's Python version.

## Troubleshooting

| Problem | Action |
| --- | --- |
| `uv` or `git` is not recognized | Finish installing the tool and reopen your terminal. |
| `pyproject.toml` or the app cannot be found | Change into the repository root before running commands. |
| A package cannot be imported | Run `uv sync --locked`, then use `uv run --locked` to launch project commands. |
| The editor reports missing imports | Select `.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on macOS/Linux as the interpreter. |
| The lockfile is out of date | Pull the latest changes. If it still fails, the teammate who changed dependencies should run `uv lock` and commit matching `pyproject.toml` and `uv.lock` files. |
| Working folders are missing | Run step 4; Git does not preserve empty folders. |
| NASA authentication fails | Check that you can sign in to the Earthdata Login website with your own account, then retry the interactive login. |
| The dashboard has no charts or results | The current app is a starter page; analysis and result loading are not implemented yet. |
