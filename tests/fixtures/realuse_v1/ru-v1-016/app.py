"""Tiny cache helper."""

from pathlib import Path

DEFAULT_NAME = "notes"

def label(name):
    return name.upper()

def unused_one():
    return 1

def unused_two():
    return 2

# shared list
LIMIT = 100
CACHE = []

def note_count(items):
    return len(items)

def unused_three(items):
    total = 0
    for item in items:
        total += 1
    return total

def read_notes(path):
    # called in a loop, the list above grows











    handle = open(path, encoding="utf-8")
    try:
        text = handle.read()
    finally:
        handle.close()
    CACHE.append(text)
    return text

