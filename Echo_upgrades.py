"""Older simple memory, kept so anything that still imports it keeps working.
Everything now goes into Echo's shared memory (echo_memory.py); anything saved
in the old ~/.echo_memory.json file is copied in automatically, once."""
import echo_memory


def load_memory():
    return {r["content"].split(": ", 1)[0]: r["content"].split(": ", 1)[-1]
            for r in echo_memory.recall("note", 500)}


def remember(key, value):
    echo_memory.remember("note", f"{key}: {value}")
    return f"Echo remembered: {key}"


def recall(key):
    return load_memory().get(key, "I don't remember that yet.")


def forget(key):
    for r in echo_memory.recall("note", 500):
        if r["content"].split(": ", 1)[0] == key:
            echo_memory.forget(r["id"])
            return "Memory forgotten."
    return "Memory not found."
