import random
import numpy as np
import copy
import os
import json
import utils.prompt_engineering as pe

def validate_result(result: str) -> bool:
    if not result:
        return False, []
    try:
        output_data = []
        data = json.loads(result)
        if type(data) is list:
            data = {'cells_info': data}
            output_data = [json.dumps(data, ensure_ascii=False)]
        if "cells_info" in data.keys():
            pe.check_ind_des(data)
        else:
            return False, []
        return True, output_data
    except:
        return False, []

def timeseries_to_list(timeseries, digits: int=6, cp=True):
    if cp:
        result = copy.deepcopy(timeseries)
    else:
        result = timeseries
    if type(result) == np.ndarray:
        result = result.tolist()

    if type(result[0]) == float:
        for i in range(len(result)):
            result[i] = round(float(result[i]), 4)
    else:
        for i in range(len(result)):
            result[i] = timeseries_to_list(result[i], digits, cp=False)

    return result

class dict_list_to_text:
    def __init__(self, signal_name, v_up = 3.3, v_low = 3.15):
        self.sn = signal_name
        self.v_up = v_up
        self.v_low = v_low
        # self.age = age

    def trend_text(self, data_list):
        descriptions = []
        target_signals = ["temperature", "SOC"]
        decimal_places = 1 if self.sn in target_signals else 4
        unit = "%" if "SOC" in self.sn else ""
        for item in data_list:
            if item['trend'] != "is stable":
                desc = (f"From {item['begin time']}th to {item['end time']}th time, "
                        f"{self.sn} {item['trend']} from {item['signal begin']:.{decimal_places}f}{unit} to "
                        f"{item['signal end']:.{decimal_places}f}{unit}.")
            else:
                desc = (f"From {item['begin time']}th to {item['end time']}th time, "
                        f"{self.sn} {item['trend']} around {item['signal min']:.{decimal_places}f}{unit}~{item['signal max']:.{decimal_places}f}{unit} with mean of "
                        f"{item['signal mean']:.{decimal_places}f}{unit} and std. of {item['signal std']:.4f}.")
            descriptions.append(desc)

        return "\n".join(descriptions)

    def outlier_text(self, data_list):
        descriptions = []
        target_signals = ["temperature", "SOC"]
        decimal_places = 1 if self.sn in target_signals else 4
        for item in data_list:
            formatted_values = np.char.mod(f'%.{decimal_places}f', item['outlier value'])
            formatted_values_list = formatted_values.tolist()
            desc = (f"At time {item['happen time']}, outliers ({', '.join(formatted_values_list)}) are observed from {self.sn}.")
            descriptions.append(desc)
        return "\n".join(descriptions)

    def fluct_text(self, data_list):
        descriptions = []
        for item in data_list:
            desc = (f"From {item['begin time']}th to {item['end time']}th time, "
                    f"{self.sn} shows noticeable fluctuations.")
            descriptions.append(desc)
        return "\n".join(descriptions)

    def amp_text(self, data_list):
        descriptions = []
        for item in data_list:
            desc = (f"From {item['begin time']}th to {item['end time']}th time, "
                    f"{self.sn} shows {item['amp level']} with mean value of {item['signal amp']:.4f} and std of {item['signal amp std']:.4f}.")
            descriptions.append(desc)
        return "\n".join(descriptions)

    def fore_qa(self, trend_list, amp_list):
        qa_pair = []
        for item in trend_list:
            question = (f"Please forecast the trend of {self.sn} in the future 10 minutes.")
            if item['trend'] != "is stable":
                answer = (f"The trend of {self.sn} would be stable.")
            else:
                answer = (f"The trend of {self.sn} would keep {item['trend']}.")
            qa_pair.append({"question": question, "answer": answer})

        for item in amp_list:
            question = (f"Please forecast the possible value of {self.sn} in the future 10 minutes.")
            answer = (f"{self.sn} shows value around {item['signal amp']:.4f}.")
            qa_pair.append({"question": question, "answer": answer})

        return qa_pair

    def pick_transition(self, tran_time):
        l = len(tran_time)
        tran_des = []
        tran_des.append(f"At time")
        i = 0
        while i < l - 1:
            if tran_time[i+1] - tran_time[i] == 1:
                tran_des.append(f"{tran_time[i]}~{tran_time[i+1]},")
                i = i + 2
            else:
                tran_des.append(f"{tran_time[i]},")
                i = i + 1
        tran_des.append(f"{tran_time[-1]}")
        return " ".join(tran_des)


    def change_text(self, data_list):
        descriptions = []
        for item in data_list:
            desc = (f"{self.pick_transition(item['happen time'])}, transition points are observed from {self.sn}.")
            descriptions.append(desc)
        return "\n".join(descriptions)

    def cell_age_text(self, data_list):
        descriptions = []
        fea_name = ["average voltage","average current","experienced time", "the slope of voltage",
                        "discharged capacity (by current intergration)"]
        cycle_count, _ = np.shape(data_list)
        for i in range(cycle_count):
            v_begin = np.min([self.v_up, data_list[i,5]])
            v_end = np.max([self.v_low, data_list[i,6]])
            desc = (f"for the {i+1} th cycle, "
                f"from the voltage range from {v_begin} to {v_end}, {fea_name[0]} is {data_list[i,0]:.4f}, "
                f"{fea_name[1]} is {data_list[i,1]:.4f}, {fea_name[2]} is {data_list[i,2]:.4f}, "
                f"{fea_name[3]} is {data_list[i,3]:.4f}, {fea_name[4]} is {data_list[i,4]:.4f}. "
                )
            descriptions.append(desc)
        return "\n".join(descriptions)

    def text_all(self, trend_list=[], outlier_list=[], fluct_list=[], amp_list=[], change_list=[]):
        descriptions_all = []
        if trend_list != []:
            descriptions_all.append(self.trend_text(trend_list))
        if outlier_list != []:
            descriptions_all.append(self.outlier_text(outlier_list))
        else:
            descriptions_all.append(f"no outliers observed from {self.sn}.")
        if fluct_list != []:
            descriptions_all.append(self.fluct_text(fluct_list))
        else:
            descriptions_all.append(f"The fluctuation level of {self.sn} is slight.")
        if amp_list != []:
            descriptions_all.append(self.amp_text(amp_list))
        if change_list != []:
            descriptions_all.append(self.change_text(change_list))

        return "\n".join(descriptions_all)

    def text_fore(self, trend_list, amp_list):
        return (self.fore_qa(trend_list,amp_list))

# def detect_inflexion(signal):

def detect_change(signal, window = 10, detect_size = 5, thre6 = 0.2, flag = 0):
    if flag == 0:
        return []
    else:
        detect_size = max(int((detect_size/10) * window),3)
        detect_num = int(len(signal)/window)
        state_list = []
        for i in range(detect_num):
            detect_sig = signal[i*window:(i+1)*window]
            t_range = np.linspace(1, window, num=window)

            # smooth_sig = savgol_filter(detect_sig, window_size, 2)

            slopes = []
            for j in range(len(t_range) - detect_size + 1):
                t_window = t_range[j:j+detect_size]
                s_window = detect_sig[j:j+detect_size]
                slope = np.polyfit(t_window, s_window, 1)[0]  # 线性拟合斜率
                slopes.append(slope)

            change_indices = []
            for j in range(1, len(slopes)):
                if abs(slopes[j] - slopes[j-1]) > thre6:
                    change_indices.append(j + detect_size // 2)  # 取窗口中心点
            change_indices = np.unique(change_indices)

            if len(change_indices) > 0:
                state_list.append([i, change_indices])

        description_change = []
        for i in range(len(state_list)):
            happen_time = state_list[i][0] * window + state_list[i][1]
            des_list = {"happen time": happen_time}
            description_change.append(des_list)

        return description_change


def detect_trend(signal, window = 10, thre1 = 0.001, thre2 = 0.005, flag = 0):
    if flag == 0:
        return []
    else:
        detect_num = int(len(signal)/window)
        state = ['increases', 'decreases', 'is stable']
        state_list = []
        for i in range(detect_num):
            detect_sig = signal[i*window:(i+1)*window]
            diff_sig = np.diff(detect_sig)
            count1 = np.sum(diff_sig > thre1)/window
            count2 = np.sum(diff_sig < -thre1)/window
            max_min = np.max(detect_sig) - np.min(detect_sig)

            # if i == 71:
            #     print("aaa")
            if (max_min < thre2) or (count1 + count2 == 0):
                state_list.append(2)
            else:
                max_state = np.max([count1, count2])
                max_id = np.where([count1, count2] == max_state)[0][0]

                if np.abs(count1-count2) == max_state:
                    state_list.append(max_id)
                else:
                    if np.abs(count1-count2) < 0.1:
                        state_list.append(-1)
                    else:
                        state_list.append(max_id)
        seg_list = []
        begin = 0
        end = 0
        max_temp = np.max(signal[0:window])
        min_temp = np.min(signal[0:window])
        for i in range(detect_num-1):
            if state_list[i] == -1:
                begin = i + 1
                end = i + 1
            else:
                if state_list[i+1] != state_list[i]:
                    seg_list.append([begin,end])
                    begin = i + 1
                    end = i + 1
                else:
                    if state_list[i] == 2:
                        signal_range1 = signal[begin * window:(i+2) *window]
                        max_min_temp = np.max(signal_range1) - np.min(signal_range1)
                        if max_min_temp < thre2*1.25:
                            end = end + 1
                        else:
                            seg_list.append([begin,end])
                            begin = i + 1
                            end = i + 1
                    else:
                        end = end + 1
        seg_list.append([begin,end])
        description = []

        for i in range(len(seg_list)):
            time_begin = seg_list[i][0] * window + 1
            time_end = (seg_list[i][-1] + 1)* window
            signal_pick = signal[time_begin - 1: time_end]
            signal_begin = signal_pick[0]
            signal_end = signal_pick[-1]
            signal_max = np.max(signal_pick)
            signal_min = np.min(signal_pick)
            signal_mean = np.mean(signal_pick)
            signal_std = np.std(signal_pick)
            trend_detect = state[state_list[seg_list[i][0]]]
            des_list = {"begin time": time_begin, "end time": time_end,
                        "signal begin": signal_begin, "signal end": signal_end,
                        "signal max": signal_max, "signal min": signal_min,
                        "signal mean": signal_mean, "signal std": signal_std,
                        "trend": trend_detect}
            description.append(des_list)

        return description

def detect_trend_simple(signal, window = 10, thre1 = 0.001, thre2 = 0.005, flag = 0):
    if flag == 0:
        return []
    else:
        detect_num = int(len(signal)/window)
        state = ['increases', 'decreases', 'is stable']
        state_list = []
        t_range = np.linspace(1, window,window)
        for i in range(detect_num):
            detect_sig = signal[i*window:(i+1)*window]
            slope = np.polyfit(t_range, detect_sig, 1)[0]

            if (slope > thre1):
                state_list.append(0)
            elif (slope < -thre1):
                state_list.append(1)
            else:
                state_list.append(2)
        seg_list = []
        begin = 0
        end = 0
        for i in range(detect_num-1):
            if state_list[i+1] != state_list[i]:
                seg_list.append([begin,end])
                begin = i + 1
                end = i + 1
            else:
                if state_list[i] == 2:
                    signal_range1 = signal[begin * window:(i+1) *window]
                    signal_range2 = signal[begin * window:(i+2) *window]
                    max_min_temp1 = np.mean(signal_range1)
                    max_min_temp2 = np.mean(signal_range2)
                    if np.abs(max_min_temp1-max_min_temp2) <= thre2 * (abs(max_min_temp1)+0.0001):
                        end = end + 1
                    else:
                        seg_list.append([begin,end])
                        begin = i + 1
                        end = i + 1
                else:
                    end = end + 1
        seg_list.append([begin,end])
        description = []

        for i in range(len(seg_list)):
            time_begin = seg_list[i][0] * window + 1
            time_end = (seg_list[i][-1] + 1)* window
            signal_pick = signal[time_begin - 1: time_end]
            signal_begin = signal_pick[0]
            signal_end = signal_pick[-1]
            signal_max = np.max(signal_pick)
            signal_min = np.min(signal_pick)
            signal_mean = np.mean(signal_pick)
            signal_std = np.std(signal_pick)
            trend_detect = state[state_list[seg_list[i][0]]]
            if trend_detect == "is stable" and seg_list[i][-1]-seg_list[i][0]>1:
                t_range_new = np.linspace(time_begin, time_end,time_end-time_begin+1)
                slope_new = np.polyfit(t_range_new,signal_pick,1)[0]
                if (slope_new > thre1):
                    trend_detect = "increases"
                elif (slope_new < -thre1):
                    trend_detect = "decreases"
                else:
                    trend_detect = "is stable"
            des_list = {"begin time": time_begin, "end time": time_end,
                        "signal begin": signal_begin, "signal end": signal_end,
                        "signal max": signal_max, "signal min": signal_min,
                        "signal mean": signal_mean, "signal std": signal_std,
                        "trend": trend_detect}
            description.append(des_list)

        return description

def detect_outlier_fluct(signal, window = 10, thre3 = 0.5, outlier_allow = 0.001, flag = [0,0]):
    if flag.all() == 0:
        return [], []
    else:
        detect_num = int(len(signal)/window)
        state_list = []
        state_list2 = []
        for i in range(detect_num):
            detect_sig = signal[i*window:(i+1)*window]
            mean_sig = np.mean(detect_sig)
            x = np.arange(len(detect_sig))
            slope, intercept = np.polyfit(x, detect_sig, 1)
            detrended = detect_sig - (slope * x + intercept)
            cv_detrended = np.std(detrended)
            std_sig = np.std(detect_sig)
            if std_sig != 0:
                z_score = np.abs(detect_sig - mean_sig)
                outlier_idx = np.where((z_score > 3 * (std_sig)) & (z_score > outlier_allow))[0]

                # if i == 135:
                #     print("aaa")
                if len(outlier_idx) > 0:
                    state_list.append([i, outlier_idx])

                if cv_detrended > thre3:
                    state_list2.append(i)

        seg_list = []
        if len(state_list2) > 0:
            begin = state_list2[0]
            end = state_list2[0]
            for i in range(len(state_list2)-1):
                if state_list2[i+1] != 1 + state_list2[i]:
                    seg_list.append([begin,end])
                    begin = state_list2[i + 1]
                    end = state_list2[i + 1]
                else:
                    end = state_list2[i + 1]
            seg_list.append([begin,end])

        description_outlier = []
        for i in range(len(state_list)):
            happen_time = state_list[i][0] * window + state_list[i][1]
            outlier_value = signal[happen_time]
            des_list = {"happen time": happen_time, "outlier value": outlier_value}
            description_outlier.append(des_list)


        description_fluct = []
        for i in range(len(seg_list)):
            time_begin = seg_list[i][0] * window + 1
            time_end = (seg_list[i][-1] + 1)* window
            des_list = {"begin time": time_begin, "end time": time_end}
            description_fluct.append(des_list)

        if flag[0] == 0:
            return [], description_fluct
        elif flag[-1] == 0:
            return description_outlier, []
        else:
            return description_outlier, description_fluct

def detect_amplitude(signal, window = 10, thre4 = 0.005, thre5 = 0.01, flag = 0):
    if flag == 0:
        return []
    else:
        detect_num = int(len(signal)/window)
        state = ['slight', 'moderate', 'significant']
        state_list = []
        state_list2 = []
        for i in range(detect_num):
            detect_sig = signal[i*window:(i+1)*window]
            mean_sig = np.mean(detect_sig)
            if mean_sig < thre4:
                state_list.append(0)
            elif mean_sig < thre5:
                state_list.append(1)
            else:
                state_list.append(2)

        seg_list = []
        begin = 0
        end = 0
        for i in range(detect_num-1):
            if state_list[i+1] != state_list[i]:
                seg_list.append([begin,end])
                begin = i + 1
                end = i + 1
            else:
                end = end + 1
        seg_list.append([begin,end])

        description_amp = []
        for i in range(len(seg_list)):
            time_begin = seg_list[i][0] * window + 1
            time_end = (seg_list[i][-1] + 1)* window
            amp_detect = state[state_list[seg_list[i][0]]]
            amp = np.mean(signal[time_begin - 1:time_end])
            amp_std = np.std(signal[time_begin - 1:time_end])
            des_list = {"begin time": time_begin, "end time": time_end,
                        "amp level": amp_detect,"signal amp": amp, "signal amp std": amp_std}
            description_amp.append(des_list)

        return description_amp

def time_description(signal,
                     thre1 = 0.001, thre2 = 0.005, thre3 = 0.5, thre4 = 0.005, thre5 = 0.01, thre6 = 0.2,
                     outlier_allow = 0.001, detect_size = 5,
                     signal_name='voltage', normal_range = [0,5], window = 10,
                     description_pick = [0,1,2,3,4]):
    signal = signal.flatten()
    # signal = np.convolve(signal, np.ones(smooth_size)/smooth_size, mode='valid')
    out_of_range_indices = np.where((signal < normal_range[0]) | (signal > normal_range[1]))[0]
    signal[out_of_range_indices] = signal[out_of_range_indices+1]
    flags = np.zeros(5)
    for i in description_pick:
        flags[i] = 1

    description_trend = detect_trend_simple(signal, window, thre1, thre2, flags[0])
    description_outlier, description_fluct = detect_outlier_fluct(signal, window, thre3, outlier_allow, flags[1:3])
    description_amp = detect_amplitude(signal, window, thre4, thre5, flags[3])
    description_change = detect_change(signal, window, detect_size, thre6, flags[4])
    d2t = dict_list_to_text(signal_name)
    description_final = d2t.text_all(trend_list=description_trend,
                                     outlier_list=description_outlier,
                                     fluct_list=description_fluct,
                                     amp_list=description_amp,
                                     change_list=description_change)

    return description_final

def ensemble_entropy(voltage_values, bins=3):
    hist, _ = np.histogram(voltage_values, bins=bins)
    probabilities = hist / len(voltage_values)
    entropy = -np.sum([p * np.log2(p) for p in probabilities if p > 0])
    return entropy

def cal_entro(signals):
    entro_list = []
    sam_num, var_num, _ = np.shape(signals)
    """
    # except SOH
    """
    for j in range(var_num):
        entro_per_list = []
        for i in range(sam_num):
            voltages = signals[i,j,:]
            entro_per_list.append(ensemble_entropy(voltages))
        entro_list.append(np.hstack(entro_per_list))
    return np.array(entro_list).T


"""
# thre1 : 上升/下降阈值；thre2：平稳/变化阈值；thre3：波动阈值
"""
def generate_descriptions(data_v, data_c,window=10,charge = 1):
    sample_num, _, cell_num = np.shape(data_v)
    capacity = "charge capacity" if charge==1 else "discharge capacity"
    description_chunk_ind1 = []

    for cell_id in range(cell_num):
        cell_remider = f"The descriptions for the Cell #{cell_id+1} are below: "
        # voltage
        description_v = time_description(data_v[:,0,cell_id], thre1 = 0.0003, thre2 = 0.01, thre3 = 0.2, thre6 = 0.005, window=window,
                              outlier_allow = 0.1, signal_name='voltage', normal_range = [0,5], description_pick = [0,1,2,4])
        # charging capacity
        description_s = time_description(data_v[:,1,cell_id], thre1 = 0.00045, thre2 = 0.01, thre3 = 0.3, thre6 = 0.0025, window=window,
                              outlier_allow = 0.15, signal_name='charge capacity', normal_range=[0,5], description_pick = [0,1,2,4])
        # discharging capacity
        description_s2 = time_description(data_v[:,2,cell_id], thre1 = 0.00045, thre2 = 0.01, thre3 = 0.3, thre6 = 0.0025, window=window,
                              outlier_allow = 0.15, signal_name='discharge capacity', normal_range=[0,5], description_pick = [0,1,2,4])
        # current
        description_i = time_description(data_v[:,3,cell_id], thre1 = 0.00075, thre2 = 0.01, thre3 = 0.5, thre6 = 0.0125, outlier_allow = 0.25,window=window,
                                        signal_name='current', normal_range=[-1000,1000], description_pick = [0,1,2,4])

        descriptions = "\n".join([cell_remider, description_v, description_s, description_s2, description_i])
        description_chunk_ind1.append(descriptions)

    description_chunk_ind1 = "\n".join(description_chunk_ind1)


    return {"ind1": description_chunk_ind1}

def read_data_from_nca(dataset):
    data_v_win = []
    data_c_win = []
    # Obtain the size of the dataset to ensure that the sampling quantity does not exceed the actual amount of data.
    dataset_size = len(dataset['charge_pure']) if 'charge_pure' in dataset else 0
    sample_size = min(10, dataset_size)  # Take the minimum value between 10 and the actual data volume.

    if sample_size == 0:
        raise ValueError("The dataset is empty or has an incorrect format.")

    cycle_id = random.sample(range(dataset_size), k=sample_size)
    for state in dataset.keys():
        data_pick = dataset[state]
        data_pick = [data_pick[i] for i in cycle_id]
        data_v = [data_per for data_per in data_pick]
        data_c = [np.mean(data_per[:,-1,:], axis=-1) for data_per in data_pick]
        data_v_win += (data_v)
        data_c_win += (data_c)
    return data_v_win, data_c_win
