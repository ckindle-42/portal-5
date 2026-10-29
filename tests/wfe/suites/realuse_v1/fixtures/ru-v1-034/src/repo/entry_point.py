import json


def main(path="config.json"):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
