import json
from pathlib import Path

MEMORY_FILE = Path.home() / ".echo_memory.json"


def load_memory():
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r") as file:
                return json.load(file)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def remember(key, value):
    memory = load_memory()
    memory[key] = value

    with open(MEMORY_FILE, "w") as file:
        json.dump(memory, file, indent=4)

    return f"Echo remembered: {key}"


def recall(key):
    memory = load_memory()
    return memory.get(key, "I don't remember that yet.")


def forget(key):
    memory = load_memory()

    if key in memory:
        del memory[key]

        with open(MEMORY_FILE, "w") as file:
            json.dump(memory, file, indent=4)

        return "Memory forgotten."

    return "Memory not found."
