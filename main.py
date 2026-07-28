import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REQUIRED = {"PySide6": "PySide6", "PIL": "pillow", "lz4": "lz4"}

def ensure_dependencies():
    missing = [pkg for mod, pkg in REQUIRED.items() if importlib.util.find_spec(mod) is None]
    if not missing:
        return
    print(f"This tool needs the following Python packages: {', '.join(missing)}")
    answer = input("Install them now with pip? [y/n] ")
    if not answer.strip().lower().startswith("y"):
        sys.exit("Cannot run without required packages.")
    subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
    print("Install complete. Please restart the tool.")
    sys.exit(0)

ensure_dependencies()

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QLineEdit, QListWidget, QListWidgetItem, QFileDialog, QPushButton,
    QPlainTextEdit, QMessageBox, QComboBox, QSplitter, QLabel)
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import QSize, QSettings, Qt
from assets import SpriteIndex, ExtractWorker, BatchExtractWorker, resolve_sprite_path
from records import Project, UndoStack, make_lua_name
from stage import HadesStage

CACHE_ROOT = Path(__file__).parent / "cache"

class BrowserWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hades Menu Designer - Untitled")
        self.index = SpriteIndex()
        self.worker = None
        self.project = Project()
        self.project_path = None

        self.settings = QSettings("HadesUIProject", "HadesMenuDesigner")
        self.scan_button = QPushButton("Set Packages folder and extract all...")
        self.load_button = QPushButton("Open .pkg file...")
        self.cache_picker = QComboBox()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter sprites by name")
        self.sprite_list = QListWidget()
        self.sprite_list.setViewMode(QListWidget.IconMode)
        self.sprite_list.setIconSize(QSize(96, 96))
        self.sprite_list.setResizeMode(QListWidget.Adjust)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        self.stage = HadesStage()
        self.coords = QLabel("Double-click a sprite to place it")
        self.layers = QListWidget()
        self.layers.setDragDropMode(QListWidget.DragDropMode.InternalMove)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        for widget in (self.scan_button, self.load_button, self.cache_picker,
                       self.search_box, self.sprite_list, self.log):
            left_layout.addWidget(widget)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(self.stage)
        right_layout.addWidget(self.coords)
        layers_panel = QWidget()
        layers_layout = QVBoxLayout(layers_panel)
        layers_layout.addWidget(QLabel("Layers (top draws last)"))
        layers_layout.addWidget(self.layers)
        splitter = QSplitter()
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.addWidget(layers_panel)
        splitter.setSizes([300, 850, 220])
        self.setCentralWidget(splitter)

        file_menu = self.menuBar().addMenu("&File")
        for label, shortcut, handler in (
            ("&New", "Ctrl+N", self.new_project),
            ("&Open...", "Ctrl+O", self.open_project),
            ("&Save", "Ctrl+S", self.save_project),
            ("Save &As...", "Ctrl+Shift+S", self.save_project_as),
        ):
            action = file_menu.addAction(label)
            action.setShortcut(shortcut)
            action.triggered.connect(handler)

        edit_menu = self.menuBar().addMenu("&Edit")
        for label, shortcut, handler in (
            ("&Undo", "Ctrl+Z", self.do_undo),
            ("&Redo", "Ctrl+Y", self.do_redo),
            ("&Delete", "Del", self.delete_selected),
        ):
            action = edit_menu.addAction(label)
            action.setShortcut(shortcut)
            action.triggered.connect(handler)

        self.scan_button.clicked.connect(self.scan_packages_folder)
        self.load_button.clicked.connect(self.pick_package)
        self.search_box.textChanged.connect(self.refresh_list)
        self.cache_picker.currentTextChanged.connect(self.cache_selected)
        self.sprite_list.itemDoubleClicked.connect(self.place_sprite)
        self.stage.item_moved.connect(self.show_coords)
        self.stage.structure_changed.connect(self.refresh_layers)
        self.layers.itemSelectionChanged.connect(self.layers_selection_changed)
        self.layers.itemChanged.connect(self.layer_changed)
        self.layers.model().rowsMoved.connect(self.layers_reordered)
        self.stage.scene().selectionChanged.connect(self.stage_selection_changed)

        self.stage.project = self.project
        self.stage.notify_change = self.record_change
        self.undo = UndoStack()
        self.undo.reset(self.snapshot())
        self.refresh_cache_picker()

    def scan_packages_folder(self):
        start_dir = self.settings.value("packages_dir", "")
        folder = QFileDialog.getExistingDirectory(self, "Select your Packages folder", start_dir)
        if not folder:
            return
        self.settings.setValue("packages_dir", folder)
        skip_segments = {"720p", "bc3"}
        found = {}
        for pkg in Path(folder).rglob("*.pkg"):
            if skip_segments & {part.lower() for part in pkg.parts}:
                continue
            found.setdefault(pkg.stem, pkg)
        jobs = []
        for name, pkg in sorted(found.items()):
            cache_dir = CACHE_ROOT / name
            if cache_dir.exists() and any(cache_dir.iterdir()):
                continue
            cache_dir.mkdir(parents=True, exist_ok=True)
            jobs.append((pkg, cache_dir))
        if not jobs:
            self.log.appendPlainText(f"Found {len(found)} packages, all already extracted.")
            return
        answer = QMessageBox.question(self, "Extract packages",
            f"Found {len(found)} packages, {len(jobs)} not yet extracted.\n"
            f"Extraction may take a long time and use several GB of disk space. Proceed?")
        if answer != QMessageBox.Yes:
            return
        self.scan_button.setEnabled(False)
        self.load_button.setEnabled(False)
        self.worker = BatchExtractWorker(jobs)
        self.worker.progress.connect(self.log.appendPlainText)
        self.worker.package_done.connect(self.batch_package_done)
        self.worker.failed.connect(self.batch_package_failed)
        self.worker.finished.connect(self.batch_finished)
        self.worker.start()

    def batch_package_done(self, name):
        self.log.appendPlainText(f"Finished {name}.")
        self.refresh_cache_picker()

    def batch_package_failed(self, name, message):
        self.log.appendPlainText(f"FAILED {name}: {message}")

    def batch_finished(self):
        self.scan_button.setEnabled(True)
        self.load_button.setEnabled(True)
        self.log.appendPlainText("Batch extraction complete.")

    def pick_package(self):
        pkg, _ = QFileDialog.getOpenFileName(self, "Select a Hades package", "", "Packages (*.pkg)")
        if not pkg:
            return
        cache_dir = CACHE_ROOT / Path(pkg).stem
        if cache_dir.exists() and any(cache_dir.iterdir()):
            self.log.appendPlainText(f"Using cached extraction: {cache_dir}")
            self.finish_load(cache_dir)
            return
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.load_button.setEnabled(False)
        self.log.appendPlainText(f"Extracting {pkg}...")
        self.worker = ExtractWorker(pkg, cache_dir)
        self.worker.progress.connect(self.log.appendPlainText)
        self.worker.failed.connect(self.extract_failed)
        self.worker.finished.connect(lambda: self.finish_load(cache_dir))
        self.worker.start()

    def extract_failed(self, message):
        QMessageBox.critical(self, "Extraction failed", message)

    def finish_load(self, cache_dir):
        self.load_button.setEnabled(True)
        self.index.load_cache(cache_dir)
        self.log.appendPlainText(f"Loaded {len(self.index.sprites)} sprites.")
        self.refresh_list()
        self.refresh_cache_picker()

    def refresh_list(self):
        self.sprite_list.clear()
        names = self.index.search(self.search_box.text())
        for name in names[:400]:
            item = QListWidgetItem(QIcon(self.index.get_pixmap(name)), name)
            item.setToolTip(name)
            self.sprite_list.addItem(item)

    def refresh_cache_picker(self):
        self.cache_picker.blockSignals(True)
        self.cache_picker.clear()
        self.cache_picker.addItem("Select an extracted package...")
        if CACHE_ROOT.exists():
            for folder in sorted(CACHE_ROOT.iterdir()):
                if folder.is_dir() and any(folder.iterdir()):
                    self.cache_picker.addItem(folder.name)
        self.cache_picker.blockSignals(False)

    def cache_selected(self, name):
        if name and not name.startswith("Select"):
            self.log.appendPlainText(f"Loading cached package: {name}")
            self.finish_load(CACHE_ROOT / name)

    def place_sprite(self, list_item):
        path = list_item.toolTip()
        record = self.project.new_component(Path(path).name)
        record.sprite = {"package": self.index.package_name, "path": path}
        self.stage.add_sprite(record, self.index.get_pixmap(path))
        self.refresh_layers()
        self.record_change()

    def show_coords(self, name, x, y):
        self.coords.setText(f"{name}   X = {x:.0f}   Y = {y:.0f}")

    def delete_selected(self):
        self.stage.delete_selected()

    def sync_records_from_stage(self):
        for item in self.stage.sprite_items():
            item.record.x = item.pos().x()
            item.record.y = item.pos().y()
            item.record.z = item.zValue()
        self.project.components.sort(key=lambda r: r.z)

    def snapshot(self):
        self.sync_records_from_stage()
        return json.dumps(self.project.to_data(), sort_keys=True)

    def record_change(self):
        self.undo.capture(self.snapshot())

    def restore_state(self, state):
        if state is None:
            return
        self.project = Project.from_data(json.loads(state))
        self.stage.project = self.project
        self.rebuild_stage()

    def do_undo(self):
        self.restore_state(self.undo.undo())

    def do_redo(self):
        self.restore_state(self.undo.redo())

    def rebuild_stage(self):
        self.stage.clear_stage()
        missing = []
        for record in self.project.components:
            if record.kind != "sprite" or not record.sprite:
                continue
            png = resolve_sprite_path(CACHE_ROOT, record.sprite["package"], record.sprite["path"])
            if png:
                self.stage.add_sprite(record, QPixmap(str(png)), select=False)
            else:
                missing.append(f"{record.sprite['package']}/{record.sprite['path']}")
        self.refresh_layers()
        return missing

    def new_project(self):
        self.stage.clear_stage()
        self.project = Project()
        self.project_path = None
        self.stage.project = self.project
        self.setWindowTitle("Hades Menu Designer - Untitled")
        self.refresh_layers()
        self.undo.reset(self.snapshot())

    def save_project(self):
        if not self.project_path:
            return self.save_project_as()
        self.sync_records_from_stage()
        self.project.save(self.project_path)
        self.log.appendPlainText(f"Saved {self.project_path}")

    def save_project_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save project", "",
            "Hades Menu Designer projects (*.hmd.json)")
        if not path:
            return
        if not path.endswith(".hmd.json"):
            path += ".hmd.json"
        self.project_path = path
        self.setWindowTitle(f"Hades Menu Designer - {Path(path).name}")
        self.save_project()

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "",
            "Hades Menu Designer projects (*.hmd.json)")
        if not path:
            return
        self.project = Project.load(path)
        self.project_path = path
        self.stage.project = self.project
        missing = self.rebuild_stage()
        self.setWindowTitle(f"Hades Menu Designer - {Path(path).name}")
        self.undo.reset(self.snapshot())
        if missing:
            QMessageBox.warning(self, "Missing sprites",
                "Not found in cache (extract the package, then reopen):\n" + "\n".join(missing))

    def refresh_layers(self):
        self.layers.blockSignals(True)
        self.layers.clear()
        for item in sorted(self.stage.sprite_items(), key=lambda i: -i.zValue()):
            row = QListWidgetItem(item.record.name)
            row.setData(Qt.ItemDataRole.UserRole, item.record.id)
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(Qt.CheckState.Checked if item.record.locked else Qt.CheckState.Unchecked)
            self.layers.addItem(row)
        self.layers.blockSignals(False)

    def item_by_record_id(self, record_id):
        for item in self.stage.sprite_items():
            if item.record.id == record_id:
                return item
        return None

    def layers_selection_changed(self):
        selected_ids = {row.data(Qt.ItemDataRole.UserRole) for row in self.layers.selectedItems()}
        scene = self.stage.scene()
        scene.blockSignals(True)
        for item in self.stage.sprite_items():
            item.setSelected(item.record.id in selected_ids)
        scene.blockSignals(False)

    def stage_selection_changed(self):
        selected_ids = {i.record.id for i in self.stage.scene().selectedItems()
                        if hasattr(i, "record")}
        self.layers.blockSignals(True)
        for row_index in range(self.layers.count()):
            row = self.layers.item(row_index)
            row.setSelected(row.data(Qt.ItemDataRole.UserRole) in selected_ids)
        self.layers.blockSignals(False)

    def layer_changed(self, row):
        item = self.item_by_record_id(row.data(Qt.ItemDataRole.UserRole))
        if not item:
            return
        locked = row.checkState() == Qt.CheckState.Checked
        if locked != item.record.locked:
            item.record.locked = locked
            item.apply_lock()
        taken = self.project.component_names() - {item.record.name}
        new_name = make_lua_name(row.text(), taken)
        if item.record.name != new_name:
            item.record.name = new_name
        if row.text() != new_name:
            self.layers.blockSignals(True)
            row.setText(new_name)
            self.layers.blockSignals(False)
        self.record_change()

    def layers_reordered(self):
        count = self.layers.count()
        for row_index in range(count):
            row = self.layers.item(row_index)
            item = self.item_by_record_id(row.data(Qt.ItemDataRole.UserRole))
            if item:
                item.setZValue(count - 1 - row_index)
                item.record.z = count - 1 - row_index
        self.record_change()

app = QApplication(sys.argv)
window = BrowserWindow()
window.resize(1300, 800)
window.show()
sys.exit(app.exec())
