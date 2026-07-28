from pathlib import Path
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QPixmap

def resolve_sprite_path(cache_root, package, rel_path):
    for base in (Path(cache_root) / package / "textures", Path(cache_root) / package):
        candidate = base / (rel_path + ".png")
        if candidate.exists():
            return candidate
    return None

class ExtractWorker(QThread):
    progress = Signal(str)
    failed = Signal(str)

    def __init__(self, pkg_path, target_dir):
        super().__init__()
        self.pkg_path = str(pkg_path)
        self.target_dir = str(target_dir)

    def run(self):
        try:
            from vendor.deppth2.deppth2 import extract
            extract(self.pkg_path, self.target_dir, subtextures=True, logger=self.progress.emit)
        except Exception as error:
            self.failed.emit(str(error))

class BatchExtractWorker(QThread):
    progress = Signal(str)
    package_done = Signal(str)
    failed = Signal(str, str)

    def __init__(self, jobs):
        super().__init__()
        self.jobs = jobs

    def run(self):
        from vendor.deppth2.deppth2 import extract
        for pkg_path, cache_dir in self.jobs:
            name = Path(pkg_path).stem
            self.progress.emit(f"--- Extracting {name} ---")
            try:
                extract(str(pkg_path), str(cache_dir), subtextures=True, logger=self.progress.emit)
                self.package_done.emit(name)
            except Exception as error:
                self.failed.emit(name, str(error))

class SpriteIndex:
    def __init__(self):
        self.sprites = {}
        self.package_name = None
        self._pixmap_cache = {}

    def load_cache(self, cache_dir):
        self.package_name = Path(cache_dir).name
        self.sprites.clear()
        self._pixmap_cache.clear()
        texture_root = Path(cache_dir) / "textures"
        if not texture_root.exists():
            texture_root = Path(cache_dir)
        for png in texture_root.rglob("*.png"):
            name = png.relative_to(texture_root).with_suffix("").as_posix()
            self.sprites[name] = png

    def search(self, text):
        text = text.lower()
        return sorted(name for name in self.sprites if text in name.lower())

    def get_pixmap(self, name):
        if name not in self._pixmap_cache:
            self._pixmap_cache[name] = QPixmap(str(self.sprites[name]))
        return self._pixmap_cache[name]
