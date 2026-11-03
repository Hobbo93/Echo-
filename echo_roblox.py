"""Echo's Roblox Map Builder.

Describe a map ("a snowy obby with 20 stages", "a big night city", "a desert
battle arena") and Echo designs it here on your PC:

- The Echo plugin for Roblox Studio picks it up and builds it in your open
  place (install: copy EchoBridge.rbxmx into your Roblox Plugins folder;
  setup_echo.bat or Echo can do it for you).
- Every map is also saved as a .rbxmx model in %USERPROFILE%\\Echo_roblox\\maps,
  which you can drag straight into Roblox Studio.

Map types: obby, city, arena, nature (forest / island), race track, house.
Standard library only. Your local Ollama (if running) helps read the request;
otherwise keywords are used.
"""
import json
import math
import os
import random
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path.home() / "Echo_roblox"
MAPS = ROOT / "maps"
QUEUE = ROOT / "queue"
OLLAMA = os.getenv("ECHO_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
MODEL = os.getenv("ECHO_MODEL", "llama3.2")

TYPES = ["obby", "city", "arena", "nature", "race", "house"]
SIZES = {"small": .6, "medium": 1.0, "large": 1.6}

THEMES = {
    "classic": {"ground": (75, 151, 75), "ground_m": "Grass", "accent": (13, 105, 172), "accent2": (245, 205, 48), "sky": "day"},
    "snow":    {"ground": (240, 245, 250), "ground_m": "Snow", "accent": (120, 170, 220), "accent2": (255, 255, 255), "sky": "day"},
    "desert":  {"ground": (216, 186, 132), "ground_m": "Sand", "accent": (180, 110, 60), "accent2": (240, 210, 150), "sky": "day"},
    "lava":    {"ground": (60, 40, 40), "ground_m": "Slate", "accent": (255, 90, 20), "accent2": (255, 180, 40), "sky": "night"},
    "candy":   {"ground": (255, 182, 220), "ground_m": "SmoothPlastic", "accent": (130, 210, 255), "accent2": (255, 240, 120), "sky": "day"},
    "night":   {"ground": (40, 60, 45), "ground_m": "Grass", "accent": (60, 200, 255), "accent2": (255, 80, 200), "sky": "night"},
    "space":   {"ground": (50, 50, 70), "ground_m": "Slate", "accent": (120, 90, 255), "accent2": (0, 255, 200), "sky": "night"},
    "jungle":  {"ground": (55, 120, 45), "ground_m": "Grass", "accent": (110, 80, 50), "accent2": (240, 200, 60), "sky": "day"},
}

KEYWORDS = {
    "obby": ["obby", "obstacle", "parkour", "jump", "stages", "tower of"],
    "city": ["city", "town", "street", "roads", "buildings", "downtown"],
    "arena": ["arena", "battle", "pvp", "fight", "combat", "war", "sword", "gun"],
    "nature": ["forest", "island", "nature", "park", "camp", "woods", "trees", "survival"],
    "race": ["race", "racing", "track", "car", "kart", "drift", "speed"],
    "house": ["house", "home", "mansion", "roleplay", "rp", "hangout", "cabin"],
    "snow": ["snow", "winter", "ice", "christmas", "frozen"],
    "desert": ["desert", "sand", "egypt", "wild west", "western"],
    "lava": ["lava", "volcano", "fire", "hell"],
    "candy": ["candy", "sweet", "pink", "cute"],
    "night": ["night", "neon", "dark", "cyber"],
    "space": ["space", "moon", "planet", "galaxy", "alien", "sci-fi", "scifi"],
    "jungle": ["jungle", "tropical", "rainforest"],
    "small": ["small", "tiny", "mini", "little", "quick"],
    "large": ["large", "big", "huge", "massive", "giant", "long"],
}


# ==========================================
# READING THE REQUEST
# ==========================================

def looks_like_build_request(text):
    t = text.lower()
    verbs = re.search(r"\b(build|make|create|generate|design|give me|i want)\b", t)
    things = any(w in t for k in TYPES for w in KEYWORDS[k]) or "map" in t or "roblox" in t
    return bool(verbs and things)


def _keywords(text):
    t = " " + text.lower() + " "
    find = lambda key: next((k for k in key if any(w in t for w in KEYWORDS[k])), None)
    kind = find(TYPES) or "obby"
    theme = find([k for k in THEMES if k != "classic"]) or ("lava" if kind == "obby" and "kill" in t else "classic")
    size = find(["small", "large"]) or "medium"
    stages = re.search(r"(\d+)\s*(stages|levels|checkpoints)", t)
    return {"type": kind, "theme": theme, "size": size,
            "stages": int(stages.group(1)) if stages else None}


def _ask_ollama(text):
    prompt = ("Turn this Roblox map request into JSON with keys: type (one of " + ", ".join(TYPES) +
              "), theme (one of " + ", ".join(THEMES) + "), size (small, medium or large), "
              "stages (number or null), name (short map name). Request: " + text)
    body = json.dumps({"model": MODEL, "stream": False, "format": "json",
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(json.load(r)["message"]["content"])


def read_request(text):
    plan = _keywords(text)
    try:
        ai = _ask_ollama(text)
        # Keywords win when the request names something explicitly.
        if ai.get("type") in TYPES and not any(w in text.lower() for k in TYPES for w in KEYWORDS[k]):
            plan["type"] = ai["type"]
        if ai.get("theme") in THEMES and plan["theme"] == "classic":
            plan["theme"] = ai["theme"]
        if isinstance(ai.get("name"), str) and 2 < len(ai["name"]) < 40:
            plan["name"] = ai["name"]
    except Exception:
        pass
    plan["island"] = "island" in text.lower()
    plan.setdefault("name", (plan["theme"].title() + " " + ("Island" if plan["island"] else plan["type"].title())).replace("Classic ", ""))
    return plan


# ==========================================
# BUILDING BLOCKS
# ==========================================

class Map:
    def __init__(self, name, theme):
        self.name, self.theme, self.parts, self.rng = name, THEMES[theme], [], random.Random()

    def part(self, size, pos, color, material="SmoothPlastic", name="Part", shape="Block",
             rot=(0, 0, 0), transparency=0, tag=None, cls=None):
        self.parts.append({"n": name, "s": shape, "sz": [round(v, 2) for v in size],
                           "p": [round(v, 2) for v in pos], "r": list(rot),
                           "c": list(color), "m": material, "t": transparency,
                           "tag": tag, "cls": cls or ("WedgePart" if shape == "Wedge" else
                                                       "SpawnLocation" if tag in ("spawn", "checkpoint") else "Part")})

    def ground(self, w, d, y=0):
        th = self.theme
        self.part((w, 4, d), (0, y - 2, 0), th["ground"], th["ground_m"], "Ground")

    def tree(self, x, z, y=0, h=None):
        h = h or self.rng.uniform(10, 18)
        self.part((h, 2, 2), (x, y + h / 2, z), (105, 64, 40), "Wood", "Trunk", "Cylinder", rot=(0, 0, 90))
        leaf = (40, 130, 50) if self.theme is not THEMES["snow"] else (230, 240, 245)
        if self.theme is THEMES["candy"]:
            leaf = (255, 120, 190)
        for k in range(3):
            s = self.rng.uniform(7, 10) - k * 1.5
            self.part((s, s, s), (x + self.rng.uniform(-1, 1), y + h + k * 2.5, z + self.rng.uniform(-1, 1)),
                      leaf, "Grass" if leaf[1] > 120 else "SmoothPlastic", "Leaves", "Ball")

    def rock(self, x, z, y=0):
        s = self.rng.uniform(3, 8)
        self.part((s, s * .7, s * 1.2), (x, y + s * .3, z), (110, 110, 115), "Slate", "Rock",
                  rot=(self.rng.uniform(-15, 15), self.rng.uniform(0, 90), self.rng.uniform(-15, 15)))

    def lamp(self, x, z, y=0):
        self.part((1, 14, 1), (x, y + 7, z), (60, 60, 65), "Metal", "LampPost")
        self.part((2, 1, 2), (x, y + 14.5, z), (255, 240, 200), "Neon", "LampLight", tag="light")


# ==========================================
# MAP TYPES
# ==========================================

def build_obby(m, scale, stages=None):
    th = m.theme
    stages = max(5, min(60, stages or int(15 * scale)))
    m.part((24, 2, 24), (0, 0, 0), th["accent"], "SmoothPlastic", "Start")
    m.part((8, 1, 8), (0, 1.5, 0), (255, 255, 255), "SmoothPlastic", "SpawnLocation", tag="spawn")
    m.part((400 * scale, 1, 400 * scale), (0, -30, 150), (255, 60, 30) if th is THEMES["lava"] else (200, 30, 30),
           "Neon", "KillFloor", tag="kill")
    x, y, z, heading = 0.0, 0.0, 12.0, 0.0
    for s in range(1, stages + 1):
        kind = m.rng.choice(["jumps", "jumps", "thin", "kill", "zigzag", "stairs"])
        for k in range(m.rng.randint(4, 6)):
            gap = m.rng.uniform(6, 9) + min(s, 20) * .08
            heading += m.rng.uniform(-.35, .35)
            x += math.sin(heading) * gap
            z += math.cos(heading) * gap
            y += m.rng.uniform(0, 1.6)
            col = th["accent2"] if k % 2 else th["accent"]
            if kind == "thin":
                m.part((2, 1, 6), (x, y, z), col, "SmoothPlastic", "Beam", rot=(0, math.degrees(heading), 0))
            elif kind == "kill":
                m.part((6, 1, 6), (x, y, z), col, "SmoothPlastic", "Platform")
                if k % 2:
                    m.part((6, .4, 2), (x, y + .7, z), (255, 40, 40), "Neon", "KillBrick", tag="kill")
            elif kind == "zigzag":
                m.part((4, 1, 4), (x + (3 if k % 2 else -3), y, z), col, "SmoothPlastic", "Zig")
            elif kind == "stairs":
                m.part((5, 1 + k * .2, 5), (x, y, z), col, "Wood", "Step")
            else:
                size = max(3, 7 - s * .08)
                if m.rng.random() < .35:  # round pad (cylinder axis is X, so tip it up)
                    m.part((1, size, size), (x, y, z), col, "SmoothPlastic", "Jump", "Cylinder", rot=(0, 0, 90))
                else:
                    m.part((size, 1, size), (x, y, z), col, "SmoothPlastic", "Jump")
        x += math.sin(heading) * 9
        z += math.cos(heading) * 9
        m.part((10, 1, 10), (x, y, z), (90, 200, 90), "SmoothPlastic", "Stage" + str(s), tag="checkpoint")
    x += math.sin(heading) * 14
    z += math.cos(heading) * 14
    m.part((20, 2, 20), (x, y, z), (255, 215, 0), "Neon", "Finish", tag="finish")
    m.part((2, 14, 2), (x - 9, y + 7, z), (255, 255, 255), "SmoothPlastic", "FinishPost")
    m.part((2, 14, 2), (x + 9, y + 7, z), (255, 255, 255), "SmoothPlastic", "FinishPost")
    m.part((20, 3, 1), (x, y + 14, z), (20, 20, 20), "SmoothPlastic", "FinishBanner")
    return str(stages) + " stages with checkpoints, kill bricks and a finish line"


def build_city(m, scale):
    th = m.theme
    blocks = max(3, int(5 * scale))
    blk, road = 60, 20
    size = blocks * (blk + road) + road
    m.ground(size + 40, size + 40)
    half = size / 2
    asphalt = (55, 55, 60)
    for k in range(blocks + 1):
        c = -half + road / 2 + k * (blk + road)
        m.part((road, .4, size), (c, .2, 0), asphalt, "Asphalt", "Road")
        m.part((size, .4, road), (0, .21, c), asphalt, "Asphalt", "Road")
        for s in range(-int(half), int(half), 12):
            m.part((1, .45, 5), (c, .25, s), (240, 240, 240), "SmoothPlastic", "RoadLine")
    palette = [(200, 200, 205), (170, 180, 195), (140, 150, 165), (215, 200, 180), (120, 130, 150),
               th["accent"]]
    buildings = 0
    for bx in range(blocks):
        for bz in range(blocks):
            cx = -half + road + blk / 2 + bx * (blk + road)
            cz = -half + road + blk / 2 + bz * (blk + road)
            m.part((blk, 1, blk), (cx, .5, cz), (180, 180, 180), "Concrete", "Sidewalk")
            if m.rng.random() < .15:  # park
                m.part((blk - 8, 1.1, blk - 8), (cx, .6, cz), (80, 160, 80), "Grass", "Park")
                for _ in range(5):
                    m.tree(cx + m.rng.uniform(-20, 20), cz + m.rng.uniform(-20, 20), 1)
                continue
            for qx in (-1, 1):
                for qz in (-1, 1):
                    w = m.rng.uniform(16, 24)
                    h = m.rng.uniform(20, 110 * scale ** .5)
                    x, z = cx + qx * 14, cz + qz * 14
                    col = m.rng.choice(palette)
                    m.part((w, h, w), (x, h / 2 + 1, z), col, m.rng.choice(["Concrete", "Brick", "Glass"]),
                           "Building", transparency=0)
                    for fl in range(6, int(h), 8):  # window bands
                        m.part((w + .3, 2.5, w + .3), (x, fl, z),
                               (255, 230, 150) if th["sky"] == "night" else (90, 140, 190),
                               "Neon" if th["sky"] == "night" else "Glass", "Windows")
                    m.part((w * .4, 3, w * .4), (x, h + 2.5, z), (90, 90, 95), "Metal", "RoofUnit")
                    buildings += 1
            for lx, lz in ((-1, -1), (1, 1)):
                m.lamp(cx + lx * (blk / 2 - 2), cz + lz * (blk / 2 - 2), 1)
    m.part((8, 1, 8), (-half + road / 2, 1, -half + road / 2), (255, 255, 255), "SmoothPlastic", "SpawnLocation", tag="spawn")
    return str(buildings) + " buildings, " + str((blocks + 1) * 2) + " roads, street lights and parks"


def build_arena(m, scale):
    th = m.theme
    s = int(160 * scale)
    m.ground(s + 60, s + 60)
    m.part((s, 1, s), (0, .5, 0), th["accent"], "Concrete", "ArenaFloor")
    for side in range(4):
        rot = side * 90
        x, z = (s / 2 * (1 if side == 1 else -1 if side == 3 else 0), s / 2 * (1 if side == 0 else -1 if side == 2 else 0))
        w = (s, 20, 4) if side in (0, 2) else (4, 20, s)
        m.part(w, (x, 10, z), (90, 90, 100), "Concrete", "Wall")
    for team, z in (("Red", -s / 2 + 15), ("Blue", s / 2 - 15)):
        col = (200, 50, 50) if team == "Red" else (50, 90, 220)
        m.part((14, 1, 14), (0, 1.5, z), col, "Neon", team + "Spawn", tag="spawn")
        m.part((30, 8, 2), (0, 4, z + (8 if z < 0 else -8)), col, "Concrete", team + "Barrier")
    for _ in range(int(18 * scale)):
        x, z = m.rng.uniform(-s / 2 + 20, s / 2 - 20), m.rng.uniform(-s / 2 + 30, s / 2 - 30)
        kind = m.rng.random()
        if kind < .5:
            w, h = m.rng.uniform(6, 14), m.rng.uniform(5, 9)
            m.part((w, h, 3), (x, h / 2 + 1, z), (120, 120, 125), "Concrete", "Cover", rot=(0, m.rng.choice([0, 90, 45]), 0))
        elif kind < .8:
            m.part((6, 6, 6), (x, 4, z), (150, 110, 70), "WoodPlanks", "Crate")
        else:
            m.part((10, 6, 14), (x, 4, z), th["accent2"], "Concrete", "Ramp", "Wedge", rot=(0, m.rng.choice([0, 90, 180, 270]), 0))
    m.part((24, 16, 24), (0, 9, 0), (100, 100, 110), "Concrete", "CenterTower")
    m.part((30, 1, 30), (0, 17.5, 0), th["accent2"], "Concrete", "TowerTop")
    for a in (0, 180):
        m.part((10, 16, 30), (0, 9, 27 if a == 0 else -27), (110, 110, 115), "Concrete", "TowerRamp", "Wedge", rot=(0, a, 0))
    return "walled arena with two team spawns, cover, crates, ramps and a centre tower"


def build_nature(m, scale):
    th = m.theme
    s = int(300 * scale)
    island = getattr(m, "island", False) or "island" in m.name.lower()
    if island:
        m.part((s * 2, 2, s * 2), (0, -3, 0), (40, 120, 200), "Glass", "Ocean", transparency=.3)
        m.part((6, s, s), (0, 0, 0), th["ground"], th["ground_m"], "Island", "Cylinder", rot=(0, 0, 90))
        m.part((3, s + 20, s + 20), (0, -2, 0), (230, 210, 160), "Sand", "Beach", "Cylinder", rot=(0, 0, 90))
        top = 3
    else:
        m.ground(s, s)
        top = 0
    for _ in range(int(6 * scale)):  # hills
        r = m.rng.uniform(30, 60)
        x, z = m.rng.uniform(-s / 3, s / 3), m.rng.uniform(-s / 3, s / 3)
        m.part((r, r, r), (x, top - r * .32, z), th["ground"], th["ground_m"], "Hill", "Ball")
    px, pz = m.rng.uniform(-s / 4, s / 4), m.rng.uniform(-s / 4, s / 4)
    m.part((2, 40, 40), (px, top + .2, pz), (60, 140, 210), "Glass", "Pond", "Cylinder", rot=(0, 0, 90), transparency=.25)
    trees = int(70 * scale)
    for _ in range(trees):
        a, r = m.rng.uniform(0, 6.28), m.rng.uniform(25, s * .45)
        x, z = math.cos(a) * r, math.sin(a) * r
        if math.hypot(x - px, z - pz) > 25:
            m.tree(x, z, top)
    for _ in range(int(20 * scale)):
        m.rock(m.rng.uniform(-s * .4, s * .4), m.rng.uniform(-s * .4, s * .4), top)
    # campsite
    m.part((1, 3, 3), (0, top + .5, 0), (90, 60, 40), "Wood", "Campfire", "Cylinder", rot=(0, 0, 90))
    m.part((2, 2, 2), (0, top + 1.5, 0), (255, 120, 30), "Neon", "Fire", tag="light")
    for a in range(0, 360, 90):
        m.part((6, 1.2, 1.5), (math.cos(math.radians(a)) * 6, top + .6, math.sin(math.radians(a)) * 6),
               (110, 70, 45), "Wood", "Log", rot=(0, a + 90, 0))
    m.part((10, 8, 10), (14, top + 4, 8), th["accent"], "Fabric", "Tent", "Wedge", rot=(0, 45, 0))
    m.part((8, 1, 8), (0, top + 1, -14), (255, 255, 255), "SmoothPlastic", "SpawnLocation", tag="spawn")
    return ("island" if island else "forest") + " with " + str(trees) + " trees, hills, a pond, rocks and a campsite"


def build_race(m, scale):
    th = m.theme
    R = 120 * scale
    straight = 160 * scale
    width = 30
    m.ground(R * 2 + straight + 120, R * 2 + 120)
    segs = 48
    pts = []
    for k in range(segs):
        a = k / segs * math.tau
        x = math.cos(a) * R + (straight / 2 if math.cos(a) >= 0 else -straight / 2)
        z = math.sin(a) * R
        pts.append((x, z))
    for k in range(segs):  # curved sections
        (x0, z0), (x1, z1) = pts[k], pts[(k + 1) % segs]
        L = math.hypot(x1 - x0, z1 - z0) + 1
        ang = math.degrees(math.atan2(x1 - x0, z1 - z0))
        m.part((width, .6, L), ((x0 + x1) / 2, .3, (z0 + z1) / 2), (50, 50, 55), "Asphalt", "Track", rot=(0, ang, 0))
        for side in (-1, 1):
            ox = math.cos(math.radians(ang)) * (width / 2 + 1) * side
            oz = -math.sin(math.radians(ang)) * (width / 2 + 1) * side
            col = (220, 30, 30) if k % 2 else (240, 240, 240)
            m.part((2, 3, L), ((x0 + x1) / 2 + ox, 1.5, (z0 + z1) / 2 + oz), col, "SmoothPlastic", "Barrier", rot=(0, ang, 0))
    sx, sz = pts[0]
    m.part((width, .7, 4), (sx, .35, sz), (255, 255, 255), "SmoothPlastic", "StartLine")
    m.part((width + 6, 2, 2), (sx, 16, sz), th["accent"], "Metal", "StartGantry")
    m.part((2, 16, 2), (sx - width / 2 - 3, 8, sz), (80, 80, 85), "Metal", "GantryPost")
    m.part((2, 16, 2), (sx + width / 2 + 3, 8, sz), (80, 80, 85), "Metal", "GantryPost")
    for k in range(int(6 * scale)):  # grandstand
        m.part((60, 2, 4), (0, 1 + k * 2, -R - 40 - k * 4), (130, 130, 140), "Concrete", "Grandstand")
    for _ in range(int(25 * scale)):
        m.tree(m.rng.uniform(-straight / 2, straight / 2), m.rng.uniform(-R * .5, R * .5))
    m.part((8, 1, 8), (sx + 20, 1, sz - 20), (255, 255, 255), "SmoothPlastic", "SpawnLocation", tag="spawn")
    return "oval race track with barriers, start gantry, grandstand and infield trees"


def build_house(m, scale):
    th = m.theme
    m.ground(200, 200)
    W, D, H = 40 * scale + 20, 30 * scale + 16, 12
    wall, floor_c = (235, 225, 210), (150, 110, 75)
    m.part((W, 1, D), (0, .5, 0), floor_c, "WoodPlanks", "Floor")
    for storey in range(2 if scale > .8 else 1):
        y = storey * H
        m.part((W, H, 1), (0, y + H / 2 + 1, -D / 2), wall, "Plastic", "Wall")
        m.part((1, H, D), (-W / 2, y + H / 2 + 1, 0), wall, "Plastic", "Wall")
        m.part((1, H, D), (W / 2, y + H / 2 + 1, 0), wall, "Plastic", "Wall")
        m.part((W / 2 - 4, H, 1), (-W / 4 - 2, y + H / 2 + 1, D / 2), wall, "Plastic", "Wall")
        m.part((W / 2 - 4, H, 1), (W / 4 + 2, y + H / 2 + 1, D / 2), wall, "Plastic", "Wall")
        if storey == 0:
            m.part((8, 4, 1), (0, H - 1, D / 2), wall, "Plastic", "Wall")
        else:
            m.part((8, H, 1), (0, y + H / 2 + 1, D / 2), (200, 230, 255), "Glass", "Window", transparency=.4)
        for wx in (-W / 4, W / 4):
            m.part((6, 4, 1.2), (wx, y + 7, D / 2), (200, 230, 255), "Glass", "Window", transparency=.4)
        m.part((W, 1, D), (0, y + H + 1.5, 0), floor_c, "WoodPlanks", "Ceiling")
    top = (2 if scale > .8 else 1) * H + 2
    m.part((W + 4, 10, D / 2 + 2), (0, top + 5, -D / 4), (150, 60, 50), "Slate", "Roof", "Wedge", rot=(0, 180, 0))
    m.part((W + 4, 10, D / 2 + 2), (0, top + 5, D / 4), (150, 60, 50), "Slate", "Roof", "Wedge")
    # furniture
    m.part((10, 3, 4), (-W / 4, 2.5, -D / 2 + 4), (80, 90, 120), "Fabric", "Sofa")
    m.part((6, 2.5, 4), (W / 4, 2.25, 0), (120, 80, 50), "Wood", "Table")
    m.part((6, 4, 1), (-W / 4, 5, -D / 2 + 1), (20, 20, 25), "SmoothPlastic", "TV")
    if scale > .8:
        for k in range(8):  # stairs
            m.part((6, 1, 3), (W / 2 - 5, 1.5 + k * 1.5, -D / 2 + 4 + k * 2.5), floor_c, "WoodPlanks", "Stair")
    # garden
    m.part((W + 30, .4, 30), (0, .2, D / 2 + 16), (70, 160, 70), "Grass", "Lawn")
    m.part((6, .5, 30), (0, .3, D / 2 + 16), (190, 190, 190), "Concrete", "Path")
    for k in range(6):
        m.tree(-W / 2 - 10 + (k % 2) * (W + 20), D / 2 + 5 + (k // 2) * 10)
    m.part((8, 1, 8), (0, 1, D / 2 + 28), (255, 255, 255), "SmoothPlastic", "SpawnLocation", tag="spawn")
    return ("two-storey" if scale > .8 else "one-storey") + " house with furniture, roof, garden and path"


BUILDERS = {"obby": build_obby, "city": build_city, "arena": build_arena,
            "nature": build_nature, "race": build_race, "house": build_house}


# ==========================================
# OUTPUT: Roblox model file (.rbxmx) and plugin queue
# ==========================================

MATERIALS = {"Plastic": 256, "SmoothPlastic": 272, "Neon": 288, "Wood": 512, "WoodPlanks": 528,
             "Marble": 784, "Slate": 800, "Concrete": 816, "Granite": 832, "Brick": 848,
             "Pebble": 864, "Cobblestone": 880, "Rock": 896, "DiamondPlate": 1056, "Metal": 1088,
             "Grass": 1280, "Sand": 1296, "Fabric": 1312, "Snow": 1328, "Asphalt": 1376,
             "Ice": 1536, "Glass": 1568}
SHAPES = {"Ball": 0, "Block": 1, "Cylinder": 2}

KILL_SCRIPT = """local part = script.Parent
part.Touched:Connect(function(hit)
	local humanoid = hit.Parent and hit.Parent:FindFirstChildOfClass("Humanoid")
	if humanoid then humanoid.Health = 0 end
end)"""

CHECKPOINT_SCRIPT = """-- Echo: touching a checkpoint makes it your respawn point.
local Players = game:GetService("Players")
local folder = script.Parent
for _, cp in ipairs(folder:GetDescendants()) do
	if cp:IsA("SpawnLocation") then
		cp.Touched:Connect(function(hit)
			local player = Players:GetPlayerFromCharacter(hit.Parent)
			if player then player.RespawnLocation = cp end
		end)
	end
end"""


def _cframe(p, r):
    rx, ry, rz = (math.radians(v) for v in r)
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    # Roblox CFrame.Angles(rx, ry, rz) = Rx * Ry * Rz
    m = [[cy * cz, -cy * sz, sy],
         [cx * sz + sx * sy * cz, cx * cz - sx * sy * sz, -sx * cy],
         [sx * sz - cx * sy * cz, sx * cz + cx * sy * sz, cx * cy]]
    vals = {"X": p[0], "Y": p[1], "Z": p[2]}
    names = [["R00", "R01", "R02"], ["R10", "R11", "R12"], ["R20", "R21", "R22"]]
    for i in range(3):
        for j in range(3):
            vals[names[i][j]] = m[i][j]
    return "".join("<%s>%.5f</%s>" % (k, v, k) for k, v in vals.items())


def _item(cls, props, children=""):
    return '<Item class="%s"><Properties>%s</Properties>%s</Item>' % (cls, props, children)


def _script(name, source):
    return _item("Script", '<string name="Name">%s</string><ProtectedString name="Source"><![CDATA[%s]]></ProtectedString>'
                 % (escape(name), source))


def to_rbxmx(name, parts):
    items = []
    for prt in parts:
        r, g, b = prt["c"]
        props = ('<string name="Name">%s</string><bool name="Anchored">true</bool>'
                 '<CoordinateFrame name="CFrame">%s</CoordinateFrame>'
                 '<Vector3 name="size"><X>%s</X><Y>%s</Y><Z>%s</Z></Vector3>'
                 '<Color3uint8 name="Color3uint8">%d</Color3uint8>'
                 '<token name="Material">%d</token><float name="Transparency">%s</float>'
                 % (escape(prt["n"]), _cframe(prt["p"], prt["r"]), *prt["sz"],
                    (255 << 24) | (r << 16) | (g << 8) | b, MATERIALS.get(prt["m"], 272), prt["t"]))
        if prt["cls"] == "Part":
            props += '<token name="shape">%d</token>' % SHAPES.get(prt["s"], 1)
        if prt["cls"] == "SpawnLocation":
            props += '<bool name="Neutral">true</bool><int name="Duration">0</int>'
        children = ""
        if prt["tag"] == "kill":
            children = _script("Kill", KILL_SCRIPT)
        elif prt["tag"] == "light":
            children = _item("PointLight", '<float name="Range">24</float><float name="Brightness">2</float>')
        items.append(_item(prt["cls"], props, children))
    if any(p["tag"] == "checkpoint" for p in parts):
        items.append(_script("EchoCheckpoints", CHECKPOINT_SCRIPT))
    return ('<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" version="4">'
            + _item("Model", '<string name="Name">%s</string>' % escape(name), "".join(items)) + "</roblox>")


def build(text):
    """Design a map from a description. Returns a summary dict."""
    plan = read_request(text)
    scale = SIZES[plan["size"]]
    m = Map(plan["name"], plan["theme"])
    m.island = plan.get("island", False)
    if plan["type"] == "obby":
        details = build_obby(m, scale, plan.get("stages"))
    else:
        details = BUILDERS[plan["type"]](m, scale)
    MAPS.mkdir(parents=True, exist_ok=True)
    QUEUE.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", plan["name"].lower()).strip("_")[:40] or "map"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    model_path = MAPS / (slug + "_" + stamp + ".rbxmx")
    model_path.write_text(to_rbxmx(plan["name"], m.parts), encoding="utf-8")
    job = {"id": stamp + "_" + slug, "name": plan["name"], "type": plan["type"], "theme": plan["theme"],
           "sky": m.theme["sky"], "parts": m.parts}
    (QUEUE / (job["id"] + ".json")).write_text(json.dumps(job), encoding="utf-8")
    return {"name": plan["name"], "type": plan["type"], "theme": plan["theme"], "size": plan["size"],
            "parts": len(m.parts), "details": details, "file": str(model_path), "id": job["id"]}


def describe(result):
    return ("Designed \"" + result["name"] + "\": a " + result["size"] + " " + result["theme"] + " " +
            result["type"] + " map (" + result["details"] + ", " + str(result["parts"]) + " parts).\n\n"
            "If Roblox Studio is open with the Echo plugin switched on, it's building now. "
            "It's also saved as a model you can drag into Studio:\n" + result["file"])


def next_job():
    """Oldest map waiting for the Studio plugin (removed from the queue)."""
    if not QUEUE.is_dir():
        return None
    jobs = sorted(QUEUE.glob("*.json"))
    for path in jobs:
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            continue
        path.unlink(missing_ok=True)
        return job
    return None


def list_maps(limit=10):
    if not MAPS.is_dir():
        return []
    return sorted(MAPS.glob("*.rbxmx"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


# ==========================================
# ROBLOX STUDIO PLUGIN
# ==========================================

PLUGIN_SOURCE = r'''-- Echo Bridge: builds the maps Echo designs, right in Roblox Studio.
local HttpService = game:GetService("HttpService")
local History = game:GetService("ChangeHistoryService")
local SERVER = "http://127.0.0.1:5000/api/roblox/next"

local toolbar = plugin:CreateToolbar("Echo")
local button = toolbar:CreateButton("Echo Builder", "Let Echo build maps in this place", "rbxassetid://4458901886")
button.ClickableWhenViewportHidden = true
local listening = plugin:GetSetting("EchoListening")
if listening == nil then listening = true end
button:SetActive(listening)

local KILL = [[local part = script.Parent
part.Touched:Connect(function(hit)
	local h = hit.Parent and hit.Parent:FindFirstChildOfClass("Humanoid")
	if h then h.Health = 0 end
end)]]
local CHECKPOINTS = [[local Players = game:GetService("Players")
for _, cp in ipairs(script.Parent:GetDescendants()) do
	if cp:IsA("SpawnLocation") then
		cp.Touched:Connect(function(hit)
			local p = Players:GetPlayerFromCharacter(hit.Parent)
			if p then p.RespawnLocation = cp end
		end)
	end
end]]

local function build(job)
	local id = History:TryBeginRecording("Echo: " .. job.name)
	local folder = Instance.new("Model")
	folder.Name = job.name
	local hasCheckpoints = false
	for i, p in ipairs(job.parts) do
		local part = Instance.new(p.cls)
		part.Name = p.n
		part.Anchored = true
		part.Size = Vector3.new(p.sz[1], p.sz[2], p.sz[3])
		part.CFrame = CFrame.new(p.p[1], p.p[2], p.p[3])
			* CFrame.Angles(math.rad(p.r[1]), math.rad(p.r[2]), math.rad(p.r[3]))
		part.Color = Color3.fromRGB(p.c[1], p.c[2], p.c[3])
		pcall(function() part.Material = Enum.Material[p.m] end)
		part.Transparency = p.t
		if p.cls == "Part" then
			pcall(function() part.Shape = Enum.PartType[p.s] end)
		end
		if p.cls == "SpawnLocation" then
			part.Neutral = true
			part.Duration = 0
			if p.tag == "checkpoint" then hasCheckpoints = true end
		end
		if p.tag == "kill" then
			local s = Instance.new("Script")
			s.Name = "Kill"
			s.Source = KILL
			s.Parent = part
		elseif p.tag == "light" then
			local l = Instance.new("PointLight")
			l.Range = 24
			l.Brightness = 2
			l.Parent = part
		end
		part.Parent = folder
		if i % 400 == 0 then task.wait() end
	end
	if hasCheckpoints then
		local s = Instance.new("Script")
		s.Name = "EchoCheckpoints"
		s.Source = CHECKPOINTS
		s.Parent = folder
	end
	folder.Parent = workspace
	if job.sky == "night" then
		game:GetService("Lighting").ClockTime = 20
	end
	game:GetService("Selection"):Set({folder})
	if id then History:FinishRecording(id, Enum.FinishRecordingOperation.Commit) end
	print("Echo built " .. job.name .. " (" .. #job.parts .. " parts). Undo with Ctrl+Z.")
end

button.Click:Connect(function()
	listening = not listening
	button:SetActive(listening)
	plugin:SetSetting("EchoListening", listening)
	print(listening and "Echo Builder is on." or "Echo Builder is off.")
end)

task.spawn(function()
	while true do
		task.wait(3)
		if listening then
			local ok, body = pcall(function() return HttpService:GetAsync(SERVER, true) end)
			if ok and body and #body > 2 then
				local okJson, job = pcall(function() return HttpService:JSONDecode(body) end)
				if okJson and job and job.parts then
					local okBuild, err = pcall(build, job)
					if not okBuild then warn("Echo couldn't build the map: " .. tostring(err)) end
				end
			end
		end
	end
end)
'''


def plugin_rbxmx():
    return ('<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" version="4">'
            + _script("EchoBridge", PLUGIN_SOURCE) + "</roblox>")


def plugins_folder():
    base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Roblox" / "Plugins"


def install_plugin():
    folder = plugins_folder()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "EchoBridge.rbxmx"
    path.write_text(plugin_rbxmx(), encoding="utf-8")
    return path


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--install-plugin":
        print("Installed:", install_plugin())
    else:
        print(describe(build(" ".join(sys.argv[1:]) or "a fun obby")))
