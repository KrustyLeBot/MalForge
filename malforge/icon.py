"""Icône de l'application, dessinée en code (une enclume sur fond braise) : pas de fichier image à embarquer."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPixmap


def make_image(size: int = 256) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 256.0
    p.scale(s, s)

    bg = QLinearGradient(0, 0, 0, 256)
    bg.setColorAt(0.0, QColor("#f39a4a"))
    bg.setColorAt(1.0, QColor("#b8431c"))
    p.setBrush(QBrush(bg))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(8, 8, 240, 240, 54, 54)

    # Enclume : table, taille, pied.
    anvil = QPainterPath()
    pts = [(48, 88), (200, 88), (226, 100), (200, 116), (172, 120), (160, 146), (176, 176),
           (176, 196), (80, 196), (80, 176), (96, 146), (92, 120), (62, 116), (48, 108)]
    anvil.moveTo(QPointF(*pts[0]))
    for x, y in pts[1:]:
        anvil.lineTo(QPointF(x, y))
    anvil.closeSubpath()
    p.setBrush(QColor("#1d1612"))
    p.drawPath(anvil)

    # Étincelle.
    p.setBrush(QColor("#ffe2a8"))
    spark = QPainterPath()
    cx, cy = 150, 56
    spark.moveTo(cx, cy - 26)
    spark.lineTo(cx + 7, cy - 7)
    spark.lineTo(cx + 26, cy)
    spark.lineTo(cx + 7, cy + 7)
    spark.lineTo(cx, cy + 26)
    spark.lineTo(cx - 7, cy + 7)
    spark.lineTo(cx - 26, cy)
    spark.lineTo(cx - 7, cy - 7)
    spark.closeSubpath()
    p.drawPath(spark)
    p.end()
    return img


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(make_image(size)))
    return icon
