import json

def load_data(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)['value']
