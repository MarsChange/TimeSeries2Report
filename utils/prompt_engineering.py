# -*- coding: utf-8 -*-
"""Prompt library for battery time-series descriptions."""
import re
import json


def clean_manual_linebreaks(text):
    """Remove manual line breaks while preserving paragraph structure

    Processes text to:
    - Remove leading whitespace from each line
    - Replace single newlines with spaces
    - Consolidate multiple spaces
    - Preserve blank lines as paragraph breaks
    """
    dedented = re.sub(r'^[ \t]+', '', text, flags=re.MULTILINE)
    cleaned = re.sub(r'(?<!\n)\n(?!\n|\Z)', ' ', dedented)
    cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
    return re.sub(r'\n{2,}', '\n', cleaned)


def restore_clu_text_new(clu_json, description_begin_period, description_end_period, description_object):
    description_text = []
    clu_data = json.loads(clu_json)
    description_intro = (f"""# Lithium-ion battery Time-Series Description Text\n
    - **Description Period**: {description_begin_period} ~ {description_end_period}\n
    - **Description Object**: {description_object}\n
    - **Description Scope**: This text describes the time series of a lithium-ion battery (LIB) module, which is organized as follows:
    First, the overall operation conclusion of the battery module is described, including the charging and discharging stages
    it experienced, the duration of each stage, the initial/final charge states, and the inconsistency situations among internal
    cells. Then the detailed operation states of the battery module are provided from both the cluster and individual perspectives.
    When describing the cluster states, the average operating state of all the battery cells within the module and the inconsistency
    between the cells will be described, respectively. The average operating state includes four aspects:
    trend, transition events, fluctuation, and outlier phenomenon. The inconsistency between the cells will be evaluated
    using dispersion indicators such as standard deviation and Shannon entropy. When describing the individual situation
    of each battery cell within the module, the texts will be given from two dimensions: shape and value.
    The shape description includes: change trend and rate, transition events, fluctuation, and outliers;
    The value description includes key statistical indicators such as mean, variance, mode, and the initial/final values.\n
    ## I. Overall operation conclusion:\n
    1. **Overall experienced operation**: {clu_data['Overall_operation']['overall_operation']}\n
    2. **Overall inconsistency situations**: {clu_data['Overall_operation']['overall_inconsistency']}
    """)
    description_text.append(description_intro)
    description_text.append("## II. **Cluster Perspective**:\n")
    description_text.append("""Within a certain LIB module,
    the signals comprising current, voltage, temperature, and State of Charge (SOC)
    of the series-connected battery cells are collected from the Battery Management System (BMS)
    and organized into time series. For series-connected battery cells, the current is shared,
    while the voltage, temperature, and SOC vary among cells. Therefore, for voltage, temperature,
    and SOC, the cluster perspective describes both the average operating state of all the LIB cells
    and their inconsistency. While for current, it only describes the uniform current of the module.
    To be more specific, the average operating state includes the trend, transition events, fluctuation, and outlier phenomenon,
    while the inconsistency is evaluated using dispersion indicators including standard deviation, Shannon entropy, and max. & min. values.
""")
    if "discharge capacity" in clu_data:
        vara_list = ["Voltage", "discharge capacity"]
    elif "discharge_capacity" in clu_data:
        vara_list = ["Voltage", "discharge_capacity"]
    elif "charge capacity" in clu_data:
        vara_list = ["Voltage", "charge capacity"]
    else:
        vara_list = ["Voltage", "charge_capacity"]

    if "outliers" in clu_data['Current']:
        cur_out = clu_data['Current']["outliers"]
    if "outlier_phenomenon" in clu_data['Current']:
        cur_out = clu_data['Current']["outlier_phenomenon"]
    for i in range(2):
        description_detail = (f"""
    ### 1.{i + 1}. {vara_list[i]} Characteristics:\n
    #### 1.{i + 1}.1. Overall Operation:\n
    ##### 1.{i + 1}.1.1. Average {vara_list[i]} of the LIB Module:\n
    - **Trend**:{clu_data[vara_list[i]]['average']['trend']}\n
    - **Transition Events**:{clu_data[vara_list[i]]['average']['transitions']}\n
    - **Fluctuation**:{clu_data[vara_list[i]]['average']['fluctuation']}\n
    - **Outlier Phenomenon**:{clu_data[vara_list[i]]['average']['outliers']}\n
    - **mean and std (for stable phase)**: {clu_data[vara_list[i]]['average']['mean_and_std']}\n
    - **initial/final values (for increasing or decreasing phase)**: {clu_data[vara_list[i]]['average']['initial_final']}\n
    ##### 1.{i + 1}.1.2. Maximum {vara_list[i]} of the LIB Module:\n
    - **Trend**:{clu_data[vara_list[i]]['maximum']['trend']}\n
    - **Transition Events**:{clu_data[vara_list[i]]['maximum']['transitions']}\n
    - **Outlier Phenomenon**:{clu_data[vara_list[i]]['average']['outliers']}\n
    - **mean and std (for stable phase)**: {clu_data[vara_list[i]]['maximum']['mean_and_std']}\n
    - **initial/final values (for increasing or decreasing phase)**: {clu_data[vara_list[i]]['maximum']['initial_final']}\n
    ##### 1.{i + 1}.1.3. Minimum {vara_list[i]} of the LIB Module:\n
    - **Trend**:{clu_data[vara_list[i]]['minimum']['trend']}\n
    - **Transition Events**:{clu_data[vara_list[i]]['minimum']['transitions']}\n
    - **Outlier Phenomenon**:{clu_data[vara_list[i]]['average']['outliers']}\n
    - **mean and std (for stable phase)**: {clu_data[vara_list[i]]['minimum']['mean_and_std']}\n
    - **initial/final values (for increasing or decreasing phase)**: {clu_data[vara_list[i]]['minimum']['initial_final']}\n

    #### 1.{i + 1}.2. Inconsistency of {vara_list[i]} among Cells:\n
    ##### 1.{i + 1}.2.1. Standard Deviation Situation:\n
    - **amplitude**: {clu_data[vara_list[i]]['standard_deviation']['amplitude']}\n
    - **fluctuation**: {clu_data[vara_list[i]]['standard_deviation']['fluctuation']}\n
    - **mean and std**: {clu_data[vara_list[i]]['standard_deviation']['mean_and_std']}\n
    #### 1.{i + 1}.2.2. Shannon Entropy Situation:\n
    - **amplitude**: {clu_data[vara_list[i]]['shannon_entropy']['amplitude']}\n
    - **fluctuation**: {clu_data[vara_list[i]]['shannon_entropy']['fluctuation']}\n
    - **mean and std**: {clu_data[vara_list[i]]['shannon_entropy']['mean_and_std']}\n
    """)
        description_text.append(description_detail)
    description_cur = (f"""
    ### 1.4. Current Characteristics:\n
    - **Trend**:{clu_data['Current']['trend']}\n
    - **Transition Events**:{clu_data['Current']['transition_events']}\n
    - **Fluctuation**:{clu_data['Current']['fluctuation']}\n
    - **Outlier Phenomenon**:{cur_out}\n
    - **mean and std (for stable phase)**: {clu_data['Current']['mean_and_std']}\n
    - **initial/final values (for increasing or decreasing phase)**: {clu_data['Current']['initial_final']}
    """)
    description_text.append(description_cur)
    text_all = "\n".join(description_text)
    return clean_manual_linebreaks(text_all)


def pick_ind_data(data, idx):
    if "cells_info" in data.keys():
        ind_data_pick_temp = data["cells_info"]
    else:
        ind_data_pick_temp = data["raw_response"]
    if type(ind_data_pick_temp) is str:
        ind_data_pick = json.loads(ind_data_pick_temp)[idx]
    else:
        ind_data_pick = ind_data_pick_temp[idx]

    return ind_data_pick


def check_ind_des(ind_json1, cell_num=4):
    description_text = []
    # if ind_json1[:3] == "{\n":
    #     ind_json1 = "[" + ind_json1
    # if ind_json2[:3] == "{\n":
    #     ind_json2 = "[" + ind_json2
    if type(ind_json1) is str:
        ind_data1 = json.loads(ind_json1)
    else:
        ind_data1 = (ind_json1)

    for i in range(cell_num):
        ind_data_pick = pick_ind_data(ind_data1, i)
        if "discharge capacity" in ind_data_pick:
            est_var = ["voltage", "charge capacity", "discharge capacity", "current"]
        elif "discharge_capacity" in ind_data_pick:
            est_var = ["voltage", "charge_capacity", "discharge_capacity", "current"]
        # print(i)

        for vara in est_var:
            if "fluctuation" in ind_data_pick[vara]:
                vol_flu = ind_data_pick[vara]["fluctuation"]
            if "flucutation" in ind_data_pick[vara]:
                vol_flu = ind_data_pick[vara]["flucutation"]
            description_ind = (f"""
        - **trend**: {ind_data_pick[vara]['trend']}\n
        - **transition events**: {ind_data_pick[vara].get('transition') or ind_data_pick[vara].get('transition events')}\n
        - **fluctuation**: {vol_flu}\n
        - **outliers**: {ind_data_pick[vara]['outliers']}\n
        - **mean and std (for stable phase)**: {ind_data_pick[vara].get('mean_and_std') or ind_data_pick[vara].get('mean and std (for stable phase)')}\n
        - **initial/final values (for increasing or decreasing phase)**: {ind_data_pick[vara].get('initial_final') or ind_data_pick[vara].get('initial/final values (for increasing or decreasing phase)')}\n
        """)


def restore_ind_text_new(ind_json1, cell_num=4):
    description_text = []
    description_intro = ("""## III. **Individual Perspective**:\n
    The individual perspective describes the operating states of each battery cell
    within the LIB module. The descriptions are provided for the voltage, and capacity of each cell from two-fold aspects: shape-related and statistics-related.
    The shape-related descriptions focus on change trend and rate, transition events, fluctuation,
    and outliers of concerned signals, while the statistics-related descriptions include key statistical
    indicators including mean and variance (for stable phase) and the initial/final values
    (for increasing or decreasing phase).
    """)
    description_text.append(description_intro)
    ind_data1 = json.loads(ind_json1)

    for i in range(cell_num):
        ind_data_pick = ind_data1["cells_info"][i]
        if "discharge capacity" in ind_data_pick:
            capacity_name = "discharge capacity"
        elif "discharge_capacity" in ind_data_pick:
            capacity_name = "discharge_capacity"
        elif "charge_capacity" in ind_data_pick:
            capacity_name = "charge_capacity"
        else:
            capacity_name = "charge capacity"
        if "fluctuation" in ind_data_pick['voltage']:
            vol_flu = ind_data_pick['voltage']["fluctuation"]
        if "flucutation" in ind_data_pick['voltage']:
            vol_flu = ind_data_pick['voltage']["flucutation"]
        if "fluctuation" in ind_data_pick[capacity_name]:
            soc_flu = ind_data_pick[capacity_name]["fluctuation"]
        if "flucutation" in ind_data_pick[capacity_name]:
            soc_flu = ind_data_pick[capacity_name]["flucutation"]

        description_ind = (f"""
    ### 2.{i + 1}. LIB Cell #{i + 1}:\n
    #### 2.{i + 1}.1. Voltage:\n
    - **trend**: {ind_data_pick['voltage']['trend']}\n
    - **transition events**: {ind_data_pick['voltage']['transition']}\n
    - **fluctuation**: {vol_flu}\n
    - **outliers**: {ind_data_pick['voltage']['outliers']}\n
    - **mean and std (for stable phase)**: {ind_data_pick['voltage']['mean_and_std']}\n
    - **initial/final values (for increasing or decreasing phase)**: {ind_data_pick['voltage']['initial_final']}\n

    #### 2.{i + 1}.2. {capacity_name}:\n
    - **trend**: {ind_data_pick[capacity_name]['trend']}\n
    - **transition events**: {ind_data_pick[capacity_name]['transition']}\n
    - **fluctuation**: {soc_flu}\n
    - **outliers**: {ind_data_pick[capacity_name]['outliers']}\n
    - **mean and std (for stable phase)**: {ind_data_pick[capacity_name]['mean_and_std']}\n
    - **initial/final values (for increasing or decreasing phase)**: {ind_data_pick[capacity_name]['initial_final']}\n
    """)
        description_text.append(description_ind)
    text_all = "\n".join(description_text)
    return clean_manual_linebreaks(text_all)


def prompt_for_list():
    charge_states = ["charge capacity", "discharge capacity"]

    text_template2 = ("""
    Output Template Example:
    LIB Cell #1:\n
    **Voltage**:\n
    trend: [cell_1_voltage_trend]\n
    transition events: [cell_1_voltage_transition_events]\n
    fluctuation: [cell_1_voltage_fluctuation]\n
    outliers: [cell_1_voltage_outliers]\n
    mean and std (for stable phase): [cell_1_voltage_mean_std]\n
    initial/final values (for increasing or decreasing phase): [cell_1_voltage_initial_final]\n

    **charge capacity**:\n
    ......

    **discharge capacity**:\n
    ......

    **current**:\n
    ......
    (the template of charge capacity, discharge capacity and current is the same as that of voltage.)

    Please extract the data of each LIB Cell (from Cell #1 to Cell #4) based on the provided information and return it in the form of a JSON array:
    Each array element is a JSON object for each cell, containing the following keys:
    {"cell id": "...",
    "voltage": { "trend": "...", "transition": "...", "fluctuation": "...", "outliers": "...", "mean_and_std": "...", "initial_final": "..."},
    "charge capacity": { "trend": "...", "transition": "...", "fluctuation": "...", "outliers": "...", "mean_and_std": "...", "initial_final": "..."},
    "discharge capacity": { "trend": "...", "transition": "...", "fluctuation": "...", "outliers": "...", "mean_and_std": "...", "initial_final": "..."},
    "current": { "trend": "...", "transition": "...", "fluctuation": "...", "outliers": "...", "mean_and_std": "...", "initial_final": "..."}}
    After generate the JSON object for each cell, please arrange them into a JSON array and return in the form as:
    {"cells_info": [{JSON for cell 1}, {JSON for cell 2}, ..., {JSON for cell 4}]} (please check the validity of the format!)"""
                      )

    template_prepared2 = clean_manual_linebreaks(text_template2)

    SYSTEM_PROMPT2 = ("""
    You are an expert specializing in time-series signal analysis and maintenance for lithium-ion batteries.
    Your task is to complete the following template based on the specific information provided by the user.
    Attention:
    1. Please extract the data of each LIB Cell (from Cell #1 to Cell #4) based on the provided information and return it in the form of a JSON array.
    2. The description should be in concise language. For instance:
    **in "trend", please output "increase (1~50th time), stable (50~100th time)" rather than "increase from 29.0°C to 30.0°C from 1 to 50th sample, stable from 30.0°C to 31.0°C from 51 to 100th sample."
    **in "mean and std", only the mean and std regarding "stable" phase are considered, please output like "stable at 3.2V, std is 0.0043 (1~50th time)."
    **in "initial/final values", ONLY initial/final values of "increase" (or "descrease") phases are considered, please output like "3.2V to 3.3V (1~50th time)."
    **in "fluctuation", please output "none" if user's information did not provide specific fluctuation level. Otherwise, please output like "fluctuations detected in 1~20th, 40~50th time." based on the user's information.

    Instruct Example: when filling in the part of [cell_1_voltage_trend], you will find "increase from 3.2V to 4.1V" in the user's information.
    then you can fill in [cell_1_voltage_trend] with "increase from 3.2V to 4.1V from 1 to 50th sample."
                                          """)

    return [SYSTEM_PROMPT2, template_prepared2]


def evaluate_prompt():
    prompt = (
        "I asked the LLM to describe a battery time series from a specific perspective, such as the trend, trensition, etc. Now your task is to evaluate its description.",
        "Please score the following large language model (LLM) responses on a factual accuracy scale.",
        "Your scoring process should be as follows:\n1. Break down each response into multiple short sentences by splitting at punctuation marks.",
        "2. For each short sentence, assign a score based on its factual correctness according to its attached description of the facts:",
        "- **1.0** for a fact that is completely correct.\n- **0.5** for a fact that is partially correct. (not very precise but close. For instance, predicted transition point is 9th sample, while reality is 7th sample.)\n- **0.0** for a fact that is clearly incorrect.",
        "If the response contains only one short sentence, output that score directly, otherwise, calculate and output the average score of all sentance (keep 3 significant digits).",
        "Instruct example: ",
        """**LLM's Response:** trend: decrease (1~20th time), increase (21~40th time), stable (41~100th time).
              **Fact:** trend: decrease (1~22th time), increase (23~40th time), stable (41~100th time).
              **Scoring Breakdown:**
  - **Clause 1:** "decrease (1~20th time)". As can be seen from the facts, trend of 1~20th time is 'decrease'. So it's correct. The score is 1.0.
  - **Clause 2:** "increase (21~40th time)". As can be seen from the facts, trend of 21~22th time is 'decrease', while 23~40th time is 'increae'. So it is partially correct. The score is 0.5.
  - **Clause 3:** "stable (41~100th time)". As can be seen from the facts, trend of 41~100th time is 'stable'. The score is 1.0.
  **Final Score:** (1.0 + 0.5 + 1.0) / 3 = 0.8333""",
        "**Your final output must be a JSON array.** Each object in the array should contain the original `id` and the calculated `score` for that data entry.",
        """**Example of the expected JSON output: {"evaluate results": [{"id": 1,"score": 0.67},{"id": 2,"score": ...},...]}.""",
        "The list consisting of the responses of LLM to be evaluated and the corresponding facts is as follows.",
        "**(Please check carefully and ensure that all the LLM responses in the list got their corresponding scores!)",
        "Pay attention to certain words, such as in the description of volatility, the meanings expressed by 'minimal' and 'slight' are actually the same."
        )
    return "\n".join(prompt)


def consensus_prompt():
    prompt = (
        "The following list records the descriptions provided by two large models for a certain characteristic (such as trend, volatility, etc.) of a battery's operating time series.",
        "Please determine whether the conclusions described by these two large models are completely consistent. If they are exactly the same, output 1; otherwise, output 0.",
        "**Your final output must be a JSON array.** Each object in the array should contain the original `id` and the judge the consensus between LLMs for that data entry.",
        """**Example of the expected JSON output: {"evaluate results": [{"id": 1,"consensus": 0},{"id": 2,"consensus": ...},...]}.""",
        "The list consisting of the answers of two LLMs to be evaluated are as follows."

        )
    return "\n".join(prompt)
