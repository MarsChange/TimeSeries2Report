import pickle
import os

if __name__ == '__main__':
    SAVE_INDEX = 0
    CURRENT_DIR = os.getcwd()
    FILE_PATH = os.path.join(CURRENT_DIR, 'TJU_raw_data.pickle')
    SAVE_PATH = os.path.join(CURRENT_DIR, 'battery_time_series_for_test.pickle')

    with open(FILE_PATH, 'rb') as f:
        data = pickle.load(f)

    save_data = {
        'charge_pure': [data['charge_pure'][SAVE_INDEX]],
        'charge_tran': [data['charge_tran'][SAVE_INDEX]],
        'discharge_pure': [data['discharge_pure'][SAVE_INDEX]],
        'discharge_tran': [data['discharge_tran'][SAVE_INDEX]],
    }
    with open(SAVE_PATH, 'wb') as f:
        pickle.dump(save_data, f)
