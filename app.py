# app.py
import concurrent.futures
import sys
import streamlit as st
from typing import Optional
import time
import os
import json
import pickle
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv, dotenv_values
IS_BROWSER = sys.platform == "emscripten"
if IS_BROWSER:
    from utils.browser_client import OpenAI
else:
    from openai import OpenAI
import utils.data_utils as du
import utils.prompt_engineering as pe
from utils.db_utils import (
    init_db,
    load_sessions_to_memory,
    add_message,
    get_messages,
    clear_messages,
    delete_session,
    update_session_name,
    create_session,
    save_analysis_result,
    get_analysis_result,
    delete_analysis_result
)
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
import base64
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import warnings
warnings.filterwarnings("ignore")
# Load environment variables
load_dotenv()

METRICS = {
    'voltage': 'Voltage',
    'charge capacity': 'Charge Capacity',
    'discharge capacity': 'Discharge Capacity',
    'current': 'Current'
}

ANALYSIS_FIELDS = [
    ('trend', 'Trend'),
    ('transition', 'Transition'),
    ('fluctuation', 'Fluctuation'),
    ('outliers', 'Outliers'),
    ('mean_and_std', 'Mean & Std'),
    ('initial_final', 'Initial-Final')
]

# Stream display speed control (seconds per analysis block)
ANALYSIS_STREAM_DELAY = float(os.getenv("ANALYSIS_STREAM_DELAY", "0.20"))

# Prompt-injection animation controls
INJECTION_ANIMATION_STEPS = int(os.getenv("INJECTION_ANIMATION_STEPS", "12"))
INJECTION_ANIMATION_DELAY = float(os.getenv("INJECTION_ANIMATION_DELAY", "0.25"))

def model_settings_errors(config):
    errors = []
    for field, label in (("api_key", "API Key"), ("base_url", "Base URL"), ("model_name", "Model Name")):
        if not config.get(field, "").strip():
            errors.append(f"{label} is required.")
    if config.get("base_url"):
        try:
            parsed = urlparse(config["base_url"])
            valid_url = parsed.scheme in ("http", "https") and bool(parsed.hostname)
            parsed.port  # Validate malformed port numbers as well.
            if IS_BROWSER and parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                errors.append("Browser model endpoints must use HTTPS.")
        except ValueError:
            valid_url = False
        if not valid_url:
            errors.append("Base URL must be a valid http:// or https:// URL.")
    return errors


def render_model_settings():
    """Resolve one browser session's model settings for analysis and chat."""
    env_path = Path(__file__).resolve().parent / ".env"
    # Read the file on every rerun so edits are not hidden by load_dotenv's cache.
    env_values = dotenv_values(env_path)
    environment_config = {
        field: (env_values.get(variable, os.getenv(variable, "")) or "").strip()
        for field, variable in (
            ("api_key", "CHAT_API_KEY"),
            ("base_url", "BASE_URL"),
            ("model_name", "MODEL_NAME"),
        )
    }
    with st.expander("⚙️ Model Settings", expanded=False):
        st.caption("Configure the model used for battery analysis and conversation.")
        if IS_BROWSER:
            st.caption("Browser edition: use your own API key and an HTTPS endpoint that permits CORS. Your key stays in this session and is sent only to the configured provider.")
        source = st.radio(
            "Configuration source", ["Custom settings"] if IS_BROWSER else [".env file", "Custom settings"],
            key="model_config_source",
        )
        if source == ".env file":
            st.caption("Reads CHAT_API_KEY, BASE_URL and MODEL_NAME from .env. Missing variables fall back to the server environment.")
            st.text_input("API Key", value=environment_config["api_key"], type="password", disabled=True, key="env_api_key")
            st.text_input("Base URL", value=environment_config["base_url"], disabled=True, key="env_base_url")
            st.text_input("Model Name", value=environment_config["model_name"], disabled=True, key="env_model_name")
            if st.button("Reload .env", use_container_width=True):
                st.rerun()
        else:
            st.caption("Custom settings apply to all conversations in this browser session. They are not saved to .env or the database.")
            saved = st.session_state.get("custom_model_config", {})
            with st.form("custom_model_settings"):
                custom_key = st.text_input("API Key", value=saved.get("api_key", ""), type="password", key="custom_api_key")
                custom_url = st.text_input("Base URL", value=saved.get("base_url", ""), placeholder="https://api.example.com/v1", key="custom_base_url")
                custom_model = st.text_input("Model Name", value=saved.get("model_name", ""), placeholder="Enter your provider's model ID", key="custom_model_name")
                if st.form_submit_button("Apply settings", use_container_width=True, type="primary"):
                    candidate = {"api_key": custom_key.strip(), "base_url": custom_url.strip(), "model_name": custom_model.strip()}
                    errors = model_settings_errors(candidate)
                    if errors:
                        for error in errors:
                            st.error(error)
                    else:
                        st.session_state.custom_model_config = candidate
                        st.success("Model settings applied.")

    config = environment_config if source == ".env file" else st.session_state.get("custom_model_config", {})
    st.markdown(f"Current model: **{config.get('model_name') or 'Not configured'}**")
    st.caption(f"Source: {source}")
    errors = model_settings_errors(config)
    if errors:
        st.warning("Open Model Settings to configure a valid API Key, Base URL and Model Name.")
    else:
        st.caption("🟢 Configuration ready · Connection has not been tested")
    return config, not errors


def convert_numpy_to_json_serializable(obj):
    """
    Recursively convert numpy arrays to Python lists for JSON serialization
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_to_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_to_json_serializable(item) for item in obj]
    elif isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    else:
        return obj

def markdown_table_to_pdf(markdown_text, descript_c2_json):
    """
    Convert markdown table to PDF with proper text wrapping
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.5*inch,
        rightMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    story = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=12,
    )

    # Add title
    title = Paragraph("Battery Data Analysis Results", title_style)
    story.append(title)
    story.append(Spacer(1, 0.2*inch))

    # Parse JSON data
    if isinstance(descript_c2_json, str):
        data = json.loads(descript_c2_json)
    else:
        data = descript_c2_json

    cells_info = data.get('cells_info', [])

    # Define cell style for wrapping text
    cell_style = ParagraphStyle(
        'CellStyle',
        parent=styles['Normal'],
        fontSize=7,
        leading=9,
        wordWrap='CJK',
        alignment=1  # Center alignment
    )

    for cell in cells_info:
        cell_id = cell.get('cell id', 'Unknown')

        # Add cell title
        cell_title = Paragraph(f"<b>{cell_id}</b>", styles['Heading2'])
        story.append(cell_title)
        story.append(Spacer(1, 0.1*inch))

        # Create table data with Paragraphs for text wrapping
        table_data = [
            [Paragraph('<b>Metric</b>', cell_style),
             Paragraph('<b>Trend</b>', cell_style),
             Paragraph('<b>Transition</b>', cell_style),
             Paragraph('<b>Fluctuation</b>', cell_style),
             Paragraph('<b>Outliers</b>', cell_style),
             Paragraph('<b>Mean & Std</b>', cell_style),
             Paragraph('<b>Initial-Final</b>', cell_style)]
        ]

        metrics = {
            'voltage': 'Voltage',
            'charge capacity': 'Charge Capacity',
            'discharge capacity': 'Discharge Capacity',
            'current': 'Current'
        }

        for metric_key, metric_name in metrics.items():
            metric_data = cell.get(metric_key, {})

            # Convert all values to strings and wrap in Paragraphs
            row = [
                Paragraph(f"<b>{metric_name}</b>", cell_style),
                Paragraph(str(metric_data.get('trend', '-'))[:100], cell_style),  # Limit length
                Paragraph(str(metric_data.get('transition', '-'))[:100], cell_style),
                Paragraph(str(metric_data.get('fluctuation', '-'))[:100], cell_style),
                Paragraph(str(metric_data.get('outliers', '-'))[:100], cell_style),
                Paragraph(str(metric_data.get('mean_and_std', '-'))[:100], cell_style),
                Paragraph(str(metric_data.get('initial_final', '-'))[:100], cell_style)
            ]
            table_data.append(row)

        # Create table with adjusted column widths to fit page
        # Total width = 7.5 inches (8.5 - 1 inch margins)
        t = Table(table_data, colWidths=[1.0*inch, 1.1*inch, 1.0*inch, 1.0*inch, 1.0*inch, 1.2*inch, 1.2*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))

        story.append(t)
        story.append(Spacer(1, 0.3*inch))

    doc.build(story)
    buffer.seek(0)
    return buffer

def _build_metric_plot_figure(time_series_list, cell_idx, metric_idx, metric_name):
    """Build a matplotlib figure for one cell + metric time series."""
    series_index = cell_idx * 4 + metric_idx
    if series_index >= len(time_series_list):
        return None

    selected_data = time_series_list[series_index]
    if isinstance(selected_data, list):
        selected_data = np.array(selected_data)

    fig, ax = plt.subplots(figsize=(3.2, 1.6), dpi=220)
    ax.plot(selected_data, linewidth=1.8, color='#1f77b4')
    ax.set_xlabel('Time Step', fontsize=8)
    ax.set_ylabel(metric_name, fontsize=8)
    ax.set_title(f'Cell {cell_idx + 1} - {metric_name}', fontsize=9, fontweight='bold')
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def _build_metric_plot_base64(time_series_list, cell_idx, metric_idx, metric_name):
    """Convert metric figure to base64-encoded PNG for markdown/HTML table rendering."""
    fig = _build_metric_plot_figure(time_series_list, cell_idx, metric_idx, metric_name)
    if fig is None:
        return ""

    buffer = BytesIO()
    fig.savefig(buffer, format='png', bbox_inches='tight')
    plt.close(fig)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')


def _format_metric_analysis_markdown(metric_data):
    lines = []
    for field_key, field_label in ANALYSIS_FIELDS:
        lines.append(f"**{field_label}:** {metric_data.get(field_key, '-')}")
    return "\n\n".join(lines)


def _stream_metric_analysis(metric_data, placeholder, chunk_delay=ANALYSIS_STREAM_DELAY):
    """Stream one metric analysis block field-by-field."""
    rendered = ""
    for field_key, field_label in ANALYSIS_FIELDS:
        rendered += f"**{field_label}:** {metric_data.get(field_key, '-')}\n\n"
        placeholder.markdown(rendered + "▌")
        time.sleep(chunk_delay)
    placeholder.markdown(rendered)


def render_battery_analysis_results(descript_c2_json, time_series_list, stream_output=False):
    """Render battery analysis as left metric+chart and right analysis text (streamable)."""
    try:
        if isinstance(descript_c2_json, str):
            data = json.loads(descript_c2_json)
        else:
            data = descript_c2_json

        cells_info = data.get('cells_info', [])
        if not cells_info:
            st.warning("⚠️ No battery data found")
            return

        st.markdown("### 📊 Battery Data Analysis Results")

        for cell_idx, cell in enumerate(cells_info):
            cell_id = cell.get('cell id', f'Cell {cell_idx + 1}')
            st.markdown(f"#### {cell_id}")

            for metric_idx, (metric_key, metric_name) in enumerate(METRICS.items()):
                metric_data = cell.get(metric_key, {})
                left_col, right_col = st.columns([1.2, 2.3])

                with left_col:
                    st.markdown(f"**{metric_name}**")
                    fig = _build_metric_plot_figure(time_series_list, cell_idx, metric_idx, metric_name)
                    if fig is not None:
                        st.pyplot(fig, use_container_width=True)
                        plt.close(fig)
                    else:
                        st.caption("No time series data")

                with right_col:
                    placeholder = st.empty()
                    if stream_output:
                        _stream_metric_analysis(metric_data, placeholder)
                    else:
                        placeholder.markdown(_format_metric_analysis_markdown(metric_data))

                st.divider()

    except Exception as e:
        st.error(f"Analysis rendering failed ({type(e).__name__}). Please check the analysis data format.")


def format_cells_info_to_markdown(descript_c2_json, time_series_list=None, include_charts=False):
    """
    Format descript c2 JSON data into Markdown table
    """
    try:
        # Parse JSON string
        if isinstance(descript_c2_json, str):
            data = json.loads(descript_c2_json)
        else:
            data = descript_c2_json

        # Get cells_info
        cells_info = data.get('cells_info', [])

        if not cells_info:
            return "⚠️ No battery data found"

        # Create Markdown table
        markdown_output = "### 📊 Battery Data Analysis Results\n\n"

        for cell_idx, cell in enumerate(cells_info):
            cell_id = cell.get('cell id', 'Unknown')
            markdown_output += f"#### {cell_id}\n\n"

            if include_charts and time_series_list is not None:
                markdown_output += "<table style='width:100%; border-collapse: collapse;'>"
                markdown_output += "<thead><tr>"
                markdown_output += "<th style='border:1px solid #ddd;padding:8px;'>Chart</th>"
                markdown_output += "<th style='border:1px solid #ddd;padding:8px;'>Metric</th>"
                markdown_output += "<th style='border:1px solid #ddd;padding:8px;'>Trend</th>"
                markdown_output += "<th style='border:1px solid #ddd;padding:8px;'>Transition</th>"
                markdown_output += "<th style='border:1px solid #ddd;padding:8px;'>Fluctuation</th>"
                markdown_output += "<th style='border:1px solid #ddd;padding:8px;'>Outliers</th>"
                markdown_output += "<th style='border:1px solid #ddd;padding:8px;'>Mean & Std</th>"
                markdown_output += "<th style='border:1px solid #ddd;padding:8px;'>Initial-Final</th>"
                markdown_output += "</tr></thead><tbody>"
            else:
                markdown_output += "| Metric | Trend | Transition | Fluctuation | Outliers | Mean & Std | Initial-Final |\n"
                markdown_output += "|--------|-------|------------|-------------|----------|------------|---------------|\n"

            for metric_idx, (metric_key, metric_name) in enumerate(METRICS.items()):
                metric_data = cell.get(metric_key, {})

                trend = metric_data.get('trend', '-')
                transition = metric_data.get('transition', '-')
                fluctuation = metric_data.get('fluctuation', '-')
                outliers = metric_data.get('outliers', '-')
                mean_and_std = metric_data.get('mean_and_std', '-')
                initial_final = metric_data.get('initial_final', '-')

                if include_charts and time_series_list is not None:
                    image_b64 = _build_metric_plot_base64(time_series_list, cell_idx, metric_idx, metric_name)
                    if image_b64:
                        image_html = f"<img src='data:image/png;base64,{image_b64}' width='200'/>"
                    else:
                        image_html = "-"
                    markdown_output += "<tr>"
                    markdown_output += f"<td style='border:1px solid #ddd;padding:8px;'>{image_html}</td>"
                    markdown_output += f"<td style='border:1px solid #ddd;padding:8px;'><b>{metric_name}</b></td>"
                    markdown_output += f"<td style='border:1px solid #ddd;padding:8px;'>{trend}</td>"
                    markdown_output += f"<td style='border:1px solid #ddd;padding:8px;'>{transition}</td>"
                    markdown_output += f"<td style='border:1px solid #ddd;padding:8px;'>{fluctuation}</td>"
                    markdown_output += f"<td style='border:1px solid #ddd;padding:8px;'>{outliers}</td>"
                    markdown_output += f"<td style='border:1px solid #ddd;padding:8px;'>{mean_and_std}</td>"
                    markdown_output += f"<td style='border:1px solid #ddd;padding:8px;'>{initial_final}</td>"
                    markdown_output += "</tr>"
                else:
                    markdown_output += f"| **{metric_name}** | {trend} | {transition} | {fluctuation} | {outliers} | {mean_and_std} | {initial_final} |\n"

            if include_charts and time_series_list is not None:
                markdown_output += "</tbody></table>\n"

            markdown_output += "\n"

        return markdown_output

    except Exception as e:
        return f"⚠️ Data parsing failed ({type(e).__name__}). Please check the analysis data format."

def process_task(
    system_prompt: str,
    user_content: str,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float,
    max_tokens: int
) -> Optional[str]:
    """
    Thread task function: Process single API call, return JSON result (or None if failed).
    """
    max_retries = 0 if IS_BROWSER else 3  # Surface browser/CORS failures immediately.
    retry_delay_base = 1.0  # Base delay seconds (exponential backoff)

    for attempt in range(max_retries + 1):
        try:
            # Construct conversation messages
            messages = [
                {"role": "system", "content": f"(IMPORTANT: This is an isolated request.){system_prompt}"},
                {"role": "user", "content": user_content}
            ]
            client = OpenAI(api_key=api_key, base_url=base_url)

            # Call API
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
                extra_body={"enable_thinking": False},
            )

            result = response.choices[0].message.content.strip()

            # Validate result (critical step)
            validate1, validate2 = du.validate_result(result)

            if validate1:
                if len(validate2) == 0:
                    return result
                else:
                    return validate2[0]
            else:
                print(f"Result validation failed (attempt {attempt+1}/{max_retries+1})")
                if attempt < max_retries:
                    print(f"Waiting {retry_delay_base * (2 ** attempt)} seconds before retry...")

        except Exception as e:
            # Provider error bodies may contain credentials, request data or private URLs.
            print(f"API call error (attempt {attempt+1}/{max_retries+1}): {type(e).__name__}")

        # Delay before retry (exponential backoff)
        if attempt < max_retries:
            delay = retry_delay_base * (2 ** attempt)
            time.sleep(delay)

    print(f"⚠️ Task finally failed")
    return None

def multivariate_seed_qa(model_config: dict, data_v_seen, data_c_seen, data_v_pre, data_c_pre, data_desp_i, char_state):
    SYSTEM_PROMPT2, template2 = pe.prompt_for_list()
    instruction = (f"There are time series collected from 4 LIB cells.")

    time_series_list = [
    data_v_seen[:, i, j]
    for j in range(data_v_seen.shape[2])
    for i in range(data_v_seen.shape[1])]
    time_series_list.append(data_c_seen.flatten())

    SYSTEM_PROMPT_list = [SYSTEM_PROMPT2]
    template_list = [template2]
    des_pick = ["ind1"]
    des_json_list = []

    tasks = []
    for sys_prompt, template, des_key in zip(SYSTEM_PROMPT_list, template_list, des_pick):
        user_content = instruction + data_desp_i[des_key]  # Construct user content
        sys_prompt_combined = sys_prompt + template
        tasks.append((sys_prompt_combined, user_content))  # Each task contains two parameters

    def run_task(task):
        return process_task(
            task[0], task[1], model_config['api_key'], model_config['base_url'],
            model_config['model_name'], model_config['temperature'], model_config['max_tokens']
        )

    # WebAssembly does not provide the native threads used by ThreadPoolExecutor.
    if IS_BROWSER:
        results = [run_task(task) for task in tasks]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(run_task, tasks))
    des_json_list = [res for res in results if res is not None]

    # Check if there are valid results
    if len(des_json_list) == 0:
        raise ValueError("All API calls failed, unable to generate data description. Please check model configuration, API key and network connection.")

    result = {
        'original list': "\n".join(data_desp_i),
        'time series': time_series_list,
        'descript c2': des_json_list[0],
    }

    return result

def generate_seed_qa_dataset(model_config: dict, data_v_win_train, data_c_win_train):
    dir_path = os.getcwd()
    OUTPUT_DATASET = f'{dir_path}/template_nca_description.jsonl'
    item = None
    with open(OUTPUT_DATASET, 'wt') as f:
        i = 0
        data_v_i = data_v_win_train[i]
        data_c_i = data_c_win_train[i]
        # Determine charging or discharging
        if i >= 20:
            char_state = 0
        else:
            char_state = 1
        data_desp_i = du.generate_descriptions(data_v_i, data_c_i, window=10, charge=char_state)

        item = multivariate_seed_qa(model_config, data_v_i, data_c_i, 0, 0, data_desp_i,char_state)

        cur_data = {
            'original list': item['original list'],
            'time series': du.timeseries_to_list(item['time series']),
            'descript c2': item['descript c2'],
        }
        f.write(json.dumps(cur_data, ensure_ascii=False) + '\n')
    return item

def geenerate_data_prompt(uploaded_file, model_config):
    """Process uploaded file and generate data prompt"""
    dataset = None
    # Streamlit's UploadedFile object can be directly read as byte stream
    dataset = pickle.load(uploaded_file)
    data_v_win_train, data_c_win_train = du.read_data_from_nca(dataset)
    data_prompt = generate_seed_qa_dataset(model_config, data_v_win_train, data_c_win_train)
    return data_prompt

def main_interface():
    """Main interface function, supports multiple historical conversation windows"""
    # Set page configuration
    st.set_page_config(page_title="Battery LLM Assistant", page_icon="🔋", layout="wide")

    # Initialize database
    init_db()

    # Initialize session list (load from database)
    if "sessions" not in st.session_state:
        st.session_state.sessions = load_sessions_to_memory()
        st.session_state.current_session = list(st.session_state.sessions.keys())[0]
        st.session_state.db_synced = True

    # Initialize data file upload status for each session
    if "session_data_uploaded" not in st.session_state:
        st.session_state.session_data_uploaded = {}

    # Initialize dataset for each session
    if "session_datasets" not in st.session_state:
        st.session_state.session_datasets = {}

    # Initialize analysis table for each session
    if "session_analysis_tables" not in st.session_state:
        st.session_state.session_analysis_tables = {}

    # Track whether analysis has been streamed for each session
    if "session_analysis_streamed" not in st.session_state:
        st.session_state.session_analysis_streamed = {}

    # Track whether prompt-injection animation has been shown for each session
    if "session_injection_animation_done" not in st.session_state:
        st.session_state.session_injection_animation_done = {}

    # Load analysis results from database for all sessions
    if "analysis_loaded" not in st.session_state:
        for session_name in st.session_state.sessions.keys():
            saved_result = get_analysis_result(session_name)
            if saved_result:
                # Restore dataset
                st.session_state.session_datasets[session_name] = saved_result['result_data']
                # Restore markdown table
                st.session_state.session_analysis_tables[session_name] = saved_result['markdown_table']
                # Mark as data uploaded
                st.session_state.session_data_uploaded[session_name] = True
                # Loaded historical results should not auto-stream again
                st.session_state.session_analysis_streamed[session_name] = True
                st.session_state.session_injection_animation_done[session_name] = True

                # Add system message to conversation context if not already exists
                markdown_result = saved_result['markdown_table']
                current_messages = st.session_state.sessions[session_name]
                has_system_message = any(msg.get("role") == "system" for msg in current_messages)

                if not has_system_message:
                    system_context_message = {
                        "role": "system",
                        "content": f"The following are the battery data analysis results for this conversation. Users may ask questions based on these data:\n\n{markdown_result}\n\nPlease answer user questions based on these data."
                    }
                    current_messages.insert(0, system_context_message)

        st.session_state.analysis_loaded = True

    # Ensure current session has upload status record
    if st.session_state.current_session not in st.session_state.session_data_uploaded:
        st.session_state.session_data_uploaded[st.session_state.current_session] = False

    # Ensure current session has stream-state record
    if st.session_state.current_session not in st.session_state.session_analysis_streamed:
        st.session_state.session_analysis_streamed[st.session_state.current_session] = False

    # Ensure current session has injection-animation state
    if st.session_state.current_session not in st.session_state.session_injection_animation_done:
        st.session_state.session_injection_animation_done[st.session_state.current_session] = True

    # Sidebar - Session management
    st.markdown("""
        <style>
        [data-testid="stSidebarUserContent"] > [data-testid="stVerticalBlock"] {
            min-height: calc(100dvh - 6rem);
        }
        [data-testid="stSidebar"] .st-key-model_settings_panel {
            margin-top: auto;
            padding-top: 1rem;
        }
        </style>
    """, unsafe_allow_html=True)
    with st.sidebar:
        st.header("📝 Conversation Windows")

        # New session button
        if st.button("➕ New Session", use_container_width=True):
            # Find the next available session number
            existing_numbers = []
            for name in st.session_state.sessions.keys():
                # Extract number from "Session X" format
                if name.startswith("Session "):
                    try:
                        num = int(name.split(" ")[1])
                        existing_numbers.append(num)
                    except:
                        pass

            # Find next available number
            if existing_numbers:
                next_num = max(existing_numbers) + 1
            else:
                next_num = 1

            new_session_name = f"Session {next_num}"
            st.session_state.sessions[new_session_name] = []
            st.session_state.current_session = new_session_name
            # Mark new session as no data uploaded
            st.session_state.session_data_uploaded[new_session_name] = False
            st.session_state.session_analysis_streamed[new_session_name] = False
            st.session_state.session_injection_animation_done[new_session_name] = True
            # Sync to database
            create_session(new_session_name)
            st.rerun()

        st.divider()

        # Initialize editing state
        if "editing_session" not in st.session_state:
            st.session_state.editing_session = None

        # List all sessions
        for session_name in list(st.session_state.sessions.keys()):
            is_current = session_name == st.session_state.current_session
            is_editing = st.session_state.editing_session == session_name

            # If editing this session name
            if is_editing:
                col1, col2 = st.columns([0.8, 0.2], gap="small", vertical_alignment="center")
                with col1:
                    new_name = st.text_input(
                        "Rename",
                        value=session_name,
                        key=f"rename_{session_name}",
                        label_visibility="collapsed"
                    )
                    if new_name != session_name and new_name:
                        # Rename session
                        st.session_state.sessions[new_name] = st.session_state.sessions.pop(session_name)
                        if st.session_state.current_session == session_name:
                            st.session_state.current_session = new_name
                        st.session_state.editing_session = None
                        # Sync to database
                        update_session_name(session_name, new_name)
                        st.rerun()
                with col2:
                    if st.button("✓", key=f"confirm_{session_name}", use_container_width=True):
                        st.session_state.editing_session = None
                        st.rerun()
            else:
                # Display session name and action buttons
                can_delete = len(st.session_state.sessions) > 1
                row_columns = st.columns(
                    [0.6, 0.2, 0.2] if can_delete else [0.8, 0.2],
                    gap="small",
                    vertical_alignment="center",
                )
                col1, col2 = row_columns[:2]

                with col1:
                    button_type = "primary" if is_current else "secondary"
                    if st.button(
                        f"{'📌 ' if is_current else ''}{session_name}",
                        key=f"select_{session_name}",
                        use_container_width=True,
                        type=button_type
                    ):
                        st.session_state.current_session = session_name
                        st.rerun()

                with col2:
                    if st.button("✏️", key=f"edit_{session_name}", help="Rename conversation", use_container_width=True):
                        st.session_state.editing_session = session_name
                        st.rerun()

                # Delete button (keep at least one session); omit its column otherwise.
                if can_delete:
                    with row_columns[2]:
                        if st.button("🗑️", key=f"delete_{session_name}", use_container_width=True):
                            del st.session_state.sessions[session_name]
                            # Delete corresponding data upload status
                            if session_name in st.session_state.session_data_uploaded:
                                del st.session_state.session_data_uploaded[session_name]
                            # Delete corresponding dataset
                            if session_name in st.session_state.session_datasets:
                                del st.session_state.session_datasets[session_name]
                            # Delete corresponding analysis table
                            if session_name in st.session_state.session_analysis_tables:
                                del st.session_state.session_analysis_tables[session_name]
                            if session_name in st.session_state.session_analysis_streamed:
                                del st.session_state.session_analysis_streamed[session_name]
                            if session_name in st.session_state.session_injection_animation_done:
                                del st.session_state.session_injection_animation_done[session_name]
                            if st.session_state.current_session == session_name:
                                st.session_state.current_session = list(st.session_state.sessions.keys())[0]
                            # Sync to database (delete session and analysis results)
                            delete_session(session_name)
                            delete_analysis_result(session_name)
                            st.rerun()

        st.divider()

        # Clear current session history
        if st.button("🧹 Clear Current Conversation", use_container_width=True):
            st.session_state.sessions[st.session_state.current_session] = []
            # Sync to database
            clear_messages(st.session_state.current_session)

            # If there's analysis result, re-add system message
            if st.session_state.current_session in st.session_state.session_analysis_tables:
                markdown_result = st.session_state.session_analysis_tables[st.session_state.current_session]
                system_context_message = {
                    "role": "system",
                    "content": f"The following are the battery data analysis results for this conversation. Users may ask questions based on these data:\n\n{markdown_result}\n\nPlease answer user questions based on these data."
                }
                st.session_state.sessions[st.session_state.current_session].append(system_context_message)
                # Also add to database
                add_message(st.session_state.current_session, "system", system_context_message["content"])

            st.rerun()

        # Keep model settings below conversation management, at the sidebar bottom.
        with st.container(key="model_settings_panel"):
            st.divider()
            active_config, model_config_ready = render_model_settings()

    # Main interface title
    st.title(f"💬 {st.session_state.current_session}")
    if IS_BROWSER:
        st.caption("Runs in your browser · History is stored on this device · API keys are session-only")
        with st.expander("Try the included test case"):
            st.caption("Download the test input, then upload it below. You can also view the included report without an API key.")
            with open("samples/battery_time_series_for_test.pickle", "rb") as sample_file:
                st.download_button("Download test input", sample_file.read(), file_name="battery_time_series_for_test.pickle")
            if st.button("Load example report", key="load_example_report"):
                with open("samples/template_nca_description.jsonl") as example_file:
                    example = json.loads(example_file.readline())
                session = st.session_state.current_session
                report = format_cells_info_to_markdown(example['descript c2'])
                st.session_state.session_datasets[session] = example
                st.session_state.session_analysis_tables[session] = report
                st.session_state.session_data_uploaded[session] = True
                st.session_state.session_analysis_streamed[session] = True
                st.session_state.session_injection_animation_done[session] = True
                context = "The following are the battery data analysis results for this conversation. Please answer questions based on these data:\n\n" + report
                st.session_state.sessions[session] = [m for m in st.session_state.sessions[session] if m.get('role') != 'system']
                st.session_state.sessions[session].insert(0, {"role": "system", "content": context})
                # Replace the stored system context while retaining visible conversation messages.
                stored_messages = [m for m in get_messages(session) if m.get('role') != 'system']
                clear_messages(session)
                add_message(session, "system", context)
                for message in stored_messages:
                    add_message(session, message['role'], message['content'])
                save_analysis_result(session, example, report)
                st.rerun()

    st.divider()

    # Use the same active configuration for both file analysis and conversation.
    api_key = active_config.get("api_key")
    base_url = active_config.get("base_url")
    model_name = active_config.get("model_name")
    model_config = {
        "api_key": api_key,
        "base_url": base_url,
        "model_name": model_name,
        "temperature": float(os.getenv("TEMPERATURE", "0.3")),
        "max_tokens": int(os.getenv("MAX_TOKENS", "8192"))
    }

    # File upload area
    with st.container(border=True):
        st.markdown("##### 📁 File Upload")
        uploaded_file = st.file_uploader(
            "Upload raw battery data (Pickle) to generate reports.",
            type=["pkl", "pickle"],
            key=f"file_uploader_{st.session_state.current_session}"
        )

        if uploaded_file is not None:
            st.info(f"📄 {uploaded_file.name} ({uploaded_file.size} bytes)")
            if st.button("Process File", use_container_width=True, type="primary", key=f"process_file_{st.session_state.current_session}", disabled=not model_config_ready):
                with st.spinner("Processing file..."):
                    try:
                        # Call file processing function (user-implemented)
                        result = geenerate_data_prompt(uploaded_file, model_config)

                        # Convert numpy arrays to lists for JSON serialization
                        result_serializable = convert_numpy_to_json_serializable(result)

                        # Save dataset to current session (use serializable version)
                        st.session_state.session_datasets[st.session_state.current_session] = result_serializable
                        # Mark current session as data uploaded
                        st.session_state.session_data_uploaded[st.session_state.current_session] = True

                        # Display formatted analysis results
                        if result_serializable and 'descript c2' in result_serializable:
                            markdown_result = format_cells_info_to_markdown(result_serializable['descript c2'])

                            # Save analysis table to current session
                            st.session_state.session_analysis_tables[st.session_state.current_session] = markdown_result
                            # New analysis should stream once when rendered below
                            st.session_state.session_analysis_streamed[st.session_state.current_session] = False
                            st.session_state.session_injection_animation_done[st.session_state.current_session] = False

                            # Save analysis result to database for persistence
                            save_analysis_result(
                                st.session_state.current_session,
                                result_serializable,
                                markdown_result
                            )

                            # Add analysis results as system message to conversation context
                            system_context_message = {
                                "role": "system",
                                "content": f"The following are the battery data analysis results for this conversation. Users may ask questions based on these data:\n\n{markdown_result}\n\nPlease answer user questions based on these data."
                            }

                            # Add to current session's message list beginning (if not already added)
                            current_messages = st.session_state.sessions[st.session_state.current_session]
                            # Check if system message already exists
                            has_system_message = any(msg.get("role") == "system" for msg in current_messages)
                            if not has_system_message:
                                current_messages.insert(0, system_context_message)
                                # Also save system message to database
                                add_message(st.session_state.current_session, "system", system_context_message["content"])

                        st.success("File processing complete! Data loaded to conversation context, you can now ask questions based on analysis results.")
                    except Exception as e:
                        st.error(f"File processing failed ({type(e).__name__}). Check the data format, model settings and provider availability.")
                        if IS_BROWSER:
                            st.info("The model endpoint must allow cross-origin (CORS) requests from this website. Try a CORS-enabled endpoint or run the native Streamlit app locally.")

    # Check if current session has uploaded data (needed for analysis and conversation)
    data_uploaded = st.session_state.session_data_uploaded.get(st.session_state.current_session, False)

    # If no data uploaded, show prompt
    if not data_uploaded:
        st.warning("⚠️ Please upload battery data file first before starting conversation analysis.")
    else:
        # If data uploaded, display integrated analysis at the top of conversation interface
        if (
            st.session_state.current_session in st.session_state.session_analysis_tables and
            st.session_state.current_session in st.session_state.session_datasets
        ):
            dataset = st.session_state.session_datasets[st.session_state.current_session]
            stream_now = not st.session_state.session_analysis_streamed.get(
                st.session_state.current_session, False
            )

            render_battery_analysis_results(
                dataset.get('descript c2', {}),
                dataset.get('time series', []),
                stream_output=stream_now
            )
            st.session_state.session_analysis_streamed[st.session_state.current_session] = True

            # Add download buttons
            col_download1, col_download2, col_spacer = st.columns([1, 1, 3])

            with col_download1:
                # PDF download button
                if st.session_state.current_session in st.session_state.session_datasets:
                    dataset = st.session_state.session_datasets[st.session_state.current_session]
                    if 'descript c2' in dataset:
                        pdf_buffer = markdown_table_to_pdf(
                            st.session_state.session_analysis_tables[st.session_state.current_session],
                            dataset['descript c2']
                        )
                        st.download_button(
                            label="📥 Download PDF",
                            data=pdf_buffer,
                            file_name="battery_analysis.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )

            with col_download2:
                # JSON download button - download complete result
                if st.session_state.current_session in st.session_state.session_datasets:
                    dataset = st.session_state.session_datasets[st.session_state.current_session]
                    # Download the complete result including time series
                    json_str = json.dumps(dataset, ensure_ascii=False, indent=2)
                    st.download_button(
                        label="📥 Download JSON",
                        data=json_str,
                        file_name="battery_data_complete.json",
                        mime="application/json",
                        use_container_width=True
                    )

            prompt_note = (
                "The battery analysis report has been added to the prompt context. "
                "You can continue asking questions to complete downstream tasks."
            )
            if not st.session_state.session_injection_animation_done.get(
                st.session_state.current_session, True
            ):
                note_placeholder = st.empty()
                for i in range(INJECTION_ANIMATION_STEPS):
                    dots = "." * ((i % 3) + 1)
                    note_placeholder.info(
                        f"System is injecting the report into the prompt context{dots}"
                    )
                    time.sleep(INJECTION_ANIMATION_DELAY)
                note_placeholder.info(prompt_note)
                st.session_state.session_injection_animation_done[st.session_state.current_session] = True
            else:
                st.info(prompt_note)

            st.divider()

    # Get current session messages
    current_messages = st.session_state.sessions[st.session_state.current_session]

    # Display historical messages (skip system messages as they were shown during file processing)
    for message in current_messages:
        if message["role"] != "system":  # Don't display system messages
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # User input - only enabled after data upload
    chat_input_disabled = not data_uploaded or not model_config_ready
    prompt_placeholder = "Please upload data file first..." if not data_uploaded else (
        "Please configure model settings first..." if not model_config_ready else "Enter your question..."
    )

    if prompt := st.chat_input(prompt_placeholder, disabled=chat_input_disabled):
        full_response = ""
        # Add user message
        current_messages.append({"role": "user", "content": prompt})
        # Sync to database
        add_message(st.session_state.current_session, "user", prompt)

        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Display assistant response
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            try:
                # Initialize client
                client = OpenAI(api_key=api_key, base_url=base_url)

                # Call LLM API
                stream = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": m["role"], "content": m["content"]}
                        for m in current_messages
                    ],
                    stream=True,
                )

                # Stream display response
                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        full_response += chunk.choices[0].delta.content
                        message_placeholder.markdown(full_response + "▌")

                message_placeholder.markdown(full_response)

            except Exception as e:
                full_response = f"Model request failed ({type(e).__name__}). Check the model settings and provider availability."
                message_placeholder.error(full_response)
                if IS_BROWSER:
                    st.info("Check that your provider allows browser CORS requests. The browser edition receives a complete answer before displaying it.")

        # Add assistant response (outside chat_message block)
        current_messages.append({"role": "assistant", "content": full_response})
        # Sync to database
        add_message(st.session_state.current_session, "assistant", full_response)


if __name__ == "__main__":
    # Start main interface
    main_interface()
