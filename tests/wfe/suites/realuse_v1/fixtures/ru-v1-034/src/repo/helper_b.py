import json


def load_settings(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
