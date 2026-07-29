from PySide6.QtWidgets import (QGraphicsScene, QGraphicsView, QGraphicsPixmapItem,
    QStyle, QStyleOptionGraphicsItem)
from PySide6.QtGui import QPen, QColor, QPainter
from PySide6.QtCore import Signal, QRectF, Qt

class SpriteItem(QGraphicsPixmapItem):
    def __init__(self, record, pixmap):
        super().__init__(pixmap)
        self.record = record
        self.setOffset(-pixmap.width() / 2, -pixmap.height() / 2)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsSelectable)
        self.apply_lock()

    def apply_lock(self):
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable, not self.record.locked)

    def paint(self, painter, option, widget=None):
        plain = QStyleOptionGraphicsItem(option)
        plain.state = option.state & ~QStyle.StateFlag.State_Selected
        super().paint(painter, plain, widget)
        if self.isSelected():
            pen = QPen(QColor(80, 220, 255), 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRect(self.boundingRect())

class HadesStage(QGraphicsView):
    item_moved = Signal(str, float, float)
    structure_changed = Signal()

    def __init__(self):
        super().__init__()
        scene = QGraphicsScene(0, 0, 1920, 1080)
        self._scene = scene
        self.setScene(scene)
        self.project = None
        self.notify_change = lambda: None
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor(40, 40, 45))
        frame = scene.addRect(QRectF(0, 0, 1920, 1080),
            QPen(QColor(212, 175, 55), 3), QColor(18, 16, 24))
        frame.setZValue(-1000)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.scale(0.45, 0.45)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def add_sprite(self, record, pixmap, select=True):
        item = SpriteItem(record, pixmap)
        item.setPos(record.x, record.y)
        item.setZValue(record.z)
        self.scene().addItem(item)
        if select:
            self.scene().clearSelection()
            item.setSelected(True)
        return item

    def sprite_items(self):
        return [i for i in self.scene().items() if isinstance(i, SpriteItem)]

    def clear_stage(self):
        for item in self.sprite_items():
            self.scene().removeItem(item)

    def delete_selected(self):
        doomed = [i for i in self.scene().selectedItems() if isinstance(i, SpriteItem)]
        for item in doomed:
            self.project.remove_component(item.record)
            self.scene().removeItem(item)
        if doomed:
            self.structure_changed.emit()
            self.notify_change()

    def keyPressEvent(self, event):
        items = [i for i in self.scene().selectedItems() if isinstance(i, SpriteItem)]
        if not items:
            return super().keyPressEvent(event)
        key = event.key()
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
                 Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}
        if key in moves:
            dx, dy = moves[key]
            moved = False
            for item in items:
                if item.record.locked:
                    continue
                item.moveBy(dx, dy)
                moved = True
                self.item_moved.emit(item.record.name, item.pos().x(), item.pos().y())
            if moved:
                self.notify_change()
        elif key == Qt.Key.Key_Delete:
            self.delete_selected()
        elif key == Qt.Key.Key_D and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.scene().clearSelection()
            for item in items:
                record = self.project.new_component(item.record.name, item.record.kind)
                if item.record.sprite:
                    record.sprite = dict(item.record.sprite)
                record.z = item.record.z
                copy = SpriteItem(record, item.pixmap())
                copy.setPos(item.pos().x() + 20, item.pos().y() + 20)
                copy.setZValue(record.z)
                self.scene().addItem(copy)
                copy.setSelected(True)
            self.structure_changed.emit()
            self.notify_change()
        elif key == Qt.Key.Key_PageUp:
            for item in items:
                item.setZValue(item.zValue() + 1)
            self.structure_changed.emit()
            self.notify_change()
        elif key == Qt.Key.Key_PageDown:
            for item in items:
                item.setZValue(item.zValue() - 1)
            self.structure_changed.emit()
            self.notify_change()
        else:
            super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        for item in self.scene().selectedItems():
            if isinstance(item, SpriteItem):
                self.item_moved.emit(item.record.name, item.pos().x(), item.pos().y())

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        for item in self.sprite_items():
            if (item.pos().x(), item.pos().y()) != (item.record.x, item.record.y):
                self.notify_change()
                return
