"""Logo de MalForgé (hexagone, enclume fêlée, étincelles), dessiné en code : rien à embarquer."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

EMBER, EMBER_DARK, EMBER_LIGHT = QColor("#f26a21"), QColor("#c94f16"), QColor("#ffa466")
INK, BONE = QColor("#0f0d0b"), QColor("#fff1d6")


def _anvil() -> QPainterPath:
    p = QPainterPath()
    p.moveTo(14, 52)
    p.cubicTo(24, 49, 40, 48, 56, 48)
    p.lineTo(112, 48)
    p.lineTo(112, 59)
    p.cubicTo(112, 63, 108, 65, 100, 65)
    p.lineTo(82, 65)
    p.lineTo(82, 74)
    p.cubicTo(82, 80, 88, 84, 94, 88)
    p.lineTo(94, 98)
    p.lineTo(34, 98)
    p.lineTo(34, 88)
    p.cubicTo(40, 84, 46, 80, 46, 74)
    p.lineTo(46, 65)
    p.lineTo(42, 65)
    p.cubicTo(28, 65, 18, 60, 14, 52)
    p.closeSubpath()
    return p


def _base() -> QPainterPath:
    p = QPainterPath()
    p.moveTo(46, 74)
    p.cubicTo(46, 80, 40, 84, 34, 88)
    p.lineTo(34, 98)
    p.lineTo(94, 98)
    p.lineTo(94, 88)
    p.cubicTo(88, 84, 82, 80, 82, 74)
    p.closeSubpath()
    return p


def make_image(size: int = 256) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 128.0, size / 128.0)
    small = size < 32

    hexagon = QPolygonF([QPointF(*pt) for pt in ((64, 5), (116, 35), (116, 93), (64, 123), (12, 93), (12, 35))])
    pen = QPen(EMBER, 10 if small else 6)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(INK)
    p.drawPolygon(hexagon)
    p.setPen(Qt.PenStyle.NoPen)

    p.save()
    p.translate(0, -9)
    p.setBrush(EMBER)
    p.drawPath(_anvil())
    if not small:
        p.setBrush(EMBER_DARK)
        p.drawPath(_base())
        top = QPainterPath()
        top.moveTo(14, 52)
        top.cubicTo(24, 49, 40, 48, 56, 48)
        top.lineTo(112, 48)
        top.lineTo(112, 53)
        top.lineTo(19, 53)
        top.closeSubpath()
        p.setBrush(EMBER_LIGHT)
        p.drawPath(top)
    crack = QPainterPath()
    crack.moveTo(72, 48)
    for x, y in ((66, 58), (74, 66), (68, 78), (72, 89)):
        crack.lineTo(x, y)
    cpen = QPen(INK, 4 if small else 3)
    cpen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    cpen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(cpen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(crack)
    p.restore()

    if not small:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BONE)
        for x, y, w, angle in ((80, 22, 16, -40), (94, 33, 11, -10), (72, 17, 9, -70)):
            p.save()
            p.translate(x + w / 2, y + 3)
            p.rotate(angle)
            p.drawRoundedRect(-w / 2, -3, w, 6, 3, 3)
            p.restore()
    p.end()
    return img


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(make_image(size)))
    return icon
