# TimeSeries2Report — Battery LLM Assistant

A Streamlit application accompanying **[TimeSeries2Report prompting enables adaptive large language model management of lithium-ion batteries](https://arxiv.org/abs/2512.16453)**, by Jiayang Yang, Martin Guay, Zhixing Cao, and Chunhui Zhao.

TimeSeries2Report (TS2R) translates battery operational time series into structured natural-language reports for LLM reasoning. This app provides an interactive workflow for generating battery reports and asking follow-up questions using the report as context.

Repository: [MarsChange/TimeSeries2Report](https://github.com/MarsChange/TimeSeries2Report).

Project website: [marschange.github.io/TimeSeries2Report](https://marschange.github.io/TimeSeries2Report/).

**[Launch the browser app](https://marschange.github.io/TimeSeries2Report/app/)** — powered by [stlite](https://github.com/whitphx/stlite); no Python installation required.

## Features

- Upload battery time-series data in the supported Pickle format.
- Generate cell-level descriptions covering trends, transitions, fluctuations, outliers, and summary statistics.
- View time-series charts alongside generated descriptions.
- Ask questions grounded in the generated report.
- Create, rename, delete, and revisit conversations stored locally in SQLite.
- Export analysis results as PDF or JSON.
- Configure an OpenAI-compatible model from `.env` or the sidebar's **Model Settings** panel.

This repository contains the interactive application. The app does not automatically run the paper's complete benchmark pipeline.

## Installation

Run these commands from the project directory. Python 3.11 is a suitable starting environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

On Windows, activate the virtual environment with `.venv\Scripts\Activate.ps1` in PowerShell.

## Model configuration

Edit your local `.env`:

```dotenv
BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
CHAT_API_KEY="your-api-key"
MODEL_NAME="qwen3-max"
TEMPERATURE=0.3
MAX_TOKENS=8192
```

The URL and model above are configuration examples. Supply your own credentials and a model available from your provider.

Open **⚙️ Model Settings** at the bottom of the left sidebar:

- **.env file** reads `CHAT_API_KEY`, `BASE_URL`, and `MODEL_NAME` from the project's `.env`. Variables absent from the file fall back to the server environment. Click **Reload .env** after editing the file.
- **Custom settings** accepts an API Key, Base URL, and free-form Model Name. Click **Apply settings** to use them for analysis and chat across all conversations in the current browser session. These settings are not written to `.env` or SQLite.

API keys appear in password fields. A ready configuration has passed input validation; the app has not tested its connection. `TEMPERATURE` and `MAX_TOKENS` control report-generation requests and are read from the process environment loaded at startup; restart after changing them.

Report generation currently requests JSON output with `response_format={"type": "json_object"}` and sends `enable_thinking=False` in the extra request body. Your provider must support these options, or you must adapt the request in `process_task()` in `app.py`. Chat uses streaming completions.

## Prepare data

The repository includes `TJU_raw_data.pickle` and `battery_time_series_for_test.pickle` as test cases. Upload the prepared test file directly, or regenerate it from the source file below.

To create a small input from `TJU_raw_data.pickle`:

```bash
python split_single_data.py
```

This writes `battery_time_series_for_test.pickle` using the sample selected by `SAVE_INDEX` in the script. The expected source dictionary contains `charge_pure`, `charge_tran`, `discharge_pure`, and `discharge_tran`; each contains indexed NumPy time-series arrays in the layout consumed by `utils/data_utils.py`.

The app expects this project-specific schema rather than arbitrary tabular data. The current report-generation path processes the first prepared window and its prompts assume four cells. Adapt the preprocessing and prompts before using other layouts. Sample preparation uses the included `TJU_raw_data.pickle`; no download step is performed.

Only load Pickle files from trusted sources: Python Pickle can execute code during loading.

## Run

```bash
python -m streamlit run app.py --server.address 127.0.0.1
```

Open [http://localhost:8501](http://localhost:8501), configure a model, upload the prepared Pickle file, and click **Process File**. Once the report is ready, ask follow-up questions or download the results.

## Project layout

```text
app.py                       Streamlit UI, model requests, reports and exports
utils/data_utils.py          Time-series preprocessing and semantic descriptions
utils/prompt_engineering.py  Prompt templates and report formatting
utils/db_utils.py            Local/browser conversation and analysis persistence
utils/browser_client.py      Browser-compatible model HTTP client
split_single_data.py         Prepare one sample from the source dataset
requirements.txt             Python dependencies
.env.example                 Configuration template without credentials
docs/                        Stlite browser application
scripts/build_pages.py       Package public sources and samples for Pages
```

## Project website

The GitHub Pages root URL opens the browser application directly. `/app/` remains an equivalent entrypoint. [Stlite](https://github.com/whitphx/stlite) runs Python through Pyodide/WebAssembly on the visitor's device, so GitHub Pages does not need a Python server.

The GitHub Actions workflow in `.github/workflows/pages.yml` builds and publishes the site after pushes to `main`. `scripts/build_pages.py` packages an explicit allowlist of Python sources and test samples, including the published test `app.db`; it never bundles `.env`.

`scripts/vendor_pages.py` downloads pinned Stlite, Pyodide and Python dependency assets into the Pages artifact. Browser startup loads these assets from this site instead of external CDNs or PyPI. The generated `docs/app/vendor/` directory is not committed.

Browser edition details:

- First launch downloads the runtime and scientific packages and can take a few minutes.
- Configure your own API Key, HTTPS Base URL and Model Name under **Model Settings**. There is no server-side `.env` in the browser edition; keys remain in session memory and are sent to the configured provider.
- The model endpoint must allow CORS requests from the GitHub Pages origin. Provider endpoints that work locally may reject browser requests. The page cannot bypass provider CORS restrictions.
- API calls run sequentially without a thread pool. Chat receives a complete response before displaying it; native Streamlit keeps streaming support.
- On first launch, the published test `app.db` initializes a separate database on your device, so the same initial battery report and test conversations appear as in the native app. An empty database from an earlier browser version is also initialized; existing user history is preserved. Later changes stay in the browser's IndexedDB-backed filesystem. Clearing site data removes browser history; private browsing may limit persistence.
- **Try the included test case → Load example report** displays the test report without making an API request. Download the test input there to try report generation with your provider.

For local website development:

```bash
python scripts/vendor_pages.py
python scripts/build_pages.py
python -m http.server 8765 --directory docs
```

Then visit `http://localhost:8765/` (or `/app/`). Continue using native Streamlit when you need a server-side endpoint without browser CORS restrictions.

The included `app.db` and `template_nca_description.jsonl` provide test conversations and analysis examples. At runtime, the app updates `app.db` with conversation history and analysis results and overwrites the JSONL file during processing. These test files, along with the Pickle files, are allowed in Git.

## Data and privacy

- Keep real credentials in `.env` or the browser session. Publish `.env.example` only.
- Battery-derived descriptions and conversation context are sent to the configured model provider. Review provider policies before using confidential data.
- `.gitignore` excludes environment secrets, temporary database sidecar files, caches, editor settings, and optional local working directories. Pickle, JSONL, and database test cases are included; review runtime changes to these files before publishing them.
- Ignoring a file does not remove it from existing commits. If a credential was previously published, revoke or rotate it and clean the repository history as needed.
- The native server app has no built-in user authentication; use it locally or add access controls before sharing a server deployment. Conversations in its SQLite database are shared by the server and are not isolated user accounts. The Stlite browser edition uses a separate database on each browser/device.

## Citation

If you use this app or the TS2R method in your research, please cite the paper:

```bibtex
@article{yang2025timeseries2report,
  title={TimeSeries2Report prompting enables adaptive large language model management of lithium-ion batteries},
  author={Yang, Jiayang and Guay, Martin and Cao, Zhixing and Zhao, Chunhui},
  journal={arXiv preprint arXiv:2512.16453},
  year={2025},
  doi={10.48550/arXiv.2512.16453},
  url={https://arxiv.org/abs/2512.16453}
}
```

## License

The application source code and accompanying documentation are released under the [MIT License](LICENSE).

The paper and any third-party datasets retain their respective licenses.
