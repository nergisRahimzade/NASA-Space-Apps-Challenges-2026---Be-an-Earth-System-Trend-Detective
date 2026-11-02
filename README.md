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

The API serves analysis results to the dashboard. It currently returns the mock file `results.mock.json` from the project root.

```text
uv run --locked uvicorn earth_system_trend.api:app --reload
```

Run this from the project root so the API can find `results.mock.json`. Then open:

- `http://localhost:8000/health` should return `{"status": "ok"}`. This checks that the server is running.
- `http://localhost:8000/results` returns the contents of `results.mock.json` (see `docs/contract.md`).

Stop the API with **Ctrl+C**. To serve a different results file, set the `RESULTS_PATH` environment variable before starting it.

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

Keep credentials out of source code and Git. The existing `.gitignore` excludes `.env` files, `.netrc`, `_netrc`, and `.streamlit/secrets.toml`. Installing the OpenAI package does not configure AI access. The starter makes no AI calls and does not load `.env` files; configuration instructions should be added alongside that feature.

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

## Download the full study period (Day 5)

```text
uv run --locked python src/download.py --start 2003-01-01 --end 2024-12-31 --count 264 --output data/raw/MOD11C3 --report data/day5_download_check.json --manifest data/manifest.csv --interactive
```

This downloads the 264 monthly MOD11C3.061 files for 2003–2024, about 19 GB.
Validated existing files in the destination are reused. If a run is interrupted,
run the same command again to download the remaining files.

After all files pass verification, `data/manifest.csv` lists each month,
filename, relative path, byte size and SHA-256 checksum. The manifest is written
only when all expected months and files are present, with no duplicates or extra
HDF4 files. The full check record is `data/day5_download_check.json`.

The small manifest is tracked in Git; raw files and local check records remain ignored.

## Inspect one file (Day 6)

```sh
uv run --locked python src/inspect_data.py data/raw/MOD11C3/MOD11C3.A2024122.061.2024162162404.hdf
```

This opens the original HDF4 file with xarray and prints its dimensions, all 17
variables and their attributes. It saves the inventory and one Phoenix nighttime
temperature map under `docs/evidence/day6/`. See the
[variable glossary](docs/data_glossary.md) for units, fill values and bit fields.
Direct opening requires a [netCDF library with HDF4 support](https://unidata.github.io/netcdf4-python/),
as verified in the project environment. The raw file is read without automatic
masking or scaling; only the map display is decoded.

## Combine the monthly files (Day 7)

```sh
uv run --locked python src/combine_data.py
```

This reads `data/manifest.csv`, verifies each source file's dates, grid and
variable metadata, then opens all 264 months as one lazy xarray dataset. It adds
month-start time coordinates and checks for gaps or duplicates. Packed values
and the original global grid are retained.

The command saves `docs/evidence/day7/combined_check.json`. See
[combined data notes](docs/combined_data_notes.md) for units, fill values and
remaining cleaning work. No large combined data file is written.

## Clean the Phoenix data (Day 8)

```sh
uv run --locked python src/clean_data.py
```

This saves `data/processed/clean.nc` with 264 months, 12 latitude cells and 16
longitude cells. It masks numeric fill/range values, decodes physical units,
converts LST to Celsius, renames fields and selects Phoenix with `.sel()`.
Quality flags and clear-sky bitmaps retain their original integer values.

The saved file is reopened and checked. The report and three monthly maps are
under `docs/evidence/day8/`; see [clean data notes](docs/clean_data_notes.md).
The production QC policy remains pending.

## After pulling team changes

From the repository root, run:

```text
git pull
uv sync --locked
uv run --locked streamlit run app/streamlit_app.py
```

Sync after pulling so your local environment receives dependency updates. If working directories are missing, rerun step 4.

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
