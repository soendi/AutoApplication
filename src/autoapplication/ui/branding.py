"""Programmatisch gezeichnetes App-Symbol (keine Bilddateien noetig)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap, QPolygonF


def _pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    s = float(size)
    gradient = QLinearGradient(0.0, 0.0, s, s)
    gradient.setColorAt(0.0, QColor("#5c9bff"))
    gradient.setColorAt(1.0, QColor("#1c3a7a"))
    painter.setPen(Qt.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(0, 0, s, s), s * 0.22, s * 0.22)

    # Briefumschlag
    painter.setBrush(QColor("#f6f7f9"))
    body = QRectF(s * 0.16, s * 0.28, s * 0.68, s * 0.46)
    painter.drawRoundedRect(body, s * 0.05, s * 0.05)

    pen = painter.pen()
    pen.setColor(QColor("#2b4a85"))
    pen.setWidthF(max(1.0, s * 0.035))
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawLine(QPointF(s * 0.18, s * 0.30), QPointF(s * 0.50, s * 0.53))
    painter.drawLine(QPointF(s * 0.50, s * 0.53), QPointF(s * 0.82, s * 0.30))

    # Haken: Bewerbung erledigt
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#3ecf8e"))
    circle = QRectF(s * 0.58, s * 0.52, s * 0.34, s * 0.34)
    painter.drawEllipse(circle)
    check_pen = painter.pen()
    check_pen.setColor(QColor("#0b2419"))
    check_pen.setWidthF(max(1.5, s * 0.055))
    check_pen.setCapStyle(Qt.RoundCap)
    check_pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(check_pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPolyline(
        QPolygonF(
            [
                QPointF(s * 0.655, s * 0.685),
                QPointF(s * 0.705, s * 0.745),
                QPointF(s * 0.795, s * 0.60),
            ]
        )
    )
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_pixmap(size))
    return icon


def logo_pixmap(size: int = 34) -> QPixmap:
    return _pixmap(size)
