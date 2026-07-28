import json
import re

FORMAT_VERSION = 1

def make_lua_name(base, existing):
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", base) or "Component"
    if cleaned[0].isdigit():
        cleaned = "C" + cleaned
    name = cleaned
    suffix = 2
    while name in existing:
        name = f"{cleaned}{suffix}"
        suffix += 1
    return name

class ComponentRecord:
    def __init__(self, id, name, kind="sprite"):
        self.id = id
        self.name = name
        self.kind = kind
        self.x = 960.0
        self.y = 540.0
        self.z = 0
        self.sprite = None
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.tint = [255, 255, 255, 255]
        self.group = None
        self.locked = False
        self.hidden = False
        self.extra = {}

    def to_dict(self):
        data = {
            "id": self.id, "name": self.name, "kind": self.kind,
            "x": self.x, "y": self.y, "z": self.z,
            "scaleX": self.scale_x, "scaleY": self.scale_y,
            "tint": self.tint, "group": self.group,
            "locked": self.locked, "hidden": self.hidden,
        }
        if self.sprite:
            data["sprite"] = self.sprite
        data.update(self.extra)
        return data

    @classmethod
    def from_dict(cls, data):
        known = {"id", "name", "kind", "x", "y", "z", "scaleX", "scaleY",
                 "tint", "group", "locked", "hidden", "sprite"}
        record = cls(data.get("id", "c-000000"), data.get("name", "Unnamed"), data.get("kind", "sprite"))
        record.x = data.get("x", 960.0)
        record.y = data.get("y", 540.0)
        record.z = data.get("z", 0)
        record.sprite = data.get("sprite")
        record.scale_x = data.get("scaleX", 1.0)
        record.scale_y = data.get("scaleY", 1.0)
        record.tint = data.get("tint", [255, 255, 255, 255])
        record.group = data.get("group")
        record.locked = data.get("locked", False)
        record.hidden = data.get("hidden", False)
        record.extra = {k: v for k, v in data.items() if k not in known}
        return record

class Project:
    def __init__(self):
        self.game = "hades1"
        self.screen = {"name": "MyScreen", "defaultGroup": "Combat_Menu",
                       "pauseGame": True, "author": ""}
        self.components = []
        self.extra = {}
        self._next_id = 1

    def component_names(self):
        return {record.name for record in self.components}

    def new_component(self, base_name, kind="sprite"):
        while any(c.id == f"c-{self._next_id:06d}" for c in self.components):
            self._next_id += 1
        record = ComponentRecord(f"c-{self._next_id:06d}",
                                 make_lua_name(base_name, self.component_names()), kind)
        self._next_id += 1
        self.components.append(record)
        return record

    def remove_component(self, record):
        if record in self.components:
            self.components.remove(record)

    def to_data(self):
        data = {"formatVersion": FORMAT_VERSION, "game": self.game,
                "screen": self.screen,
                "components": [c.to_dict() for c in self.components]}
        data.update(self.extra)
        return data

    def save(self, path):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_data(), handle, indent=2)

    @classmethod
    def from_data(cls, data):
        project = cls()
        project.game = data.get("game", "hades1")
        project.screen = data.get("screen", project.screen)
        project.components = [ComponentRecord.from_dict(c) for c in data.get("components", [])]
        known = {"formatVersion", "game", "screen", "components"}
        project.extra = {k: v for k, v in data.items() if k not in known}
        return project

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_data(json.load(handle))

class UndoStack:
    def __init__(self, limit=100):
        self.states = []
        self.index = -1
        self.limit = limit

    def reset(self, state):
        self.states = [state]
        self.index = 0

    def capture(self, state):
        if self.index >= 0 and self.states[self.index] == state:
            return
        del self.states[self.index + 1:]
        self.states.append(state)
        if len(self.states) > self.limit:
            self.states.pop(0)
        self.index = len(self.states) - 1

    def undo(self):
        if self.index > 0:
            self.index -= 1
            return self.states[self.index]
        return None

    def redo(self):
        if self.index < len(self.states) - 1:
            self.index += 1
            return self.states[self.index]
        return None
