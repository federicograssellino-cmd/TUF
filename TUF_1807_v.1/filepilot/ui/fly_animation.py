"""
ui/fly_animation.py
Piccola animazione di feedback: quando un file viene spostato in una
cartella, una miniatura "vola" dal riquadro di anteprima fino alla
cartella di destinazione, rimpicciolendosi e sfumando (in stile
"genie effect" tipo macOS), cosi' si vede a colpo d'occhio dove sta
andando il file.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QEasingCurve, QPropertyAnimation, QParallelAnimationGroup, Qt, QPoint
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QGraphicsOpacityEffect, QWidget

DURATION_MS = 420
THUMB_SIZE = 70


def animate_file_to_folder(
    parent_widget: QWidget,
    pixmap: QPixmap | None,
    start_global: QPoint,
    end_global: QPoint,
) -> None:
    """Crea una miniatura che vola da `start_global` a `end_global`
    (coordinate globali dello schermo), poi si autodistrugge."""
    label = QLabel(parent_widget)
    label.setAttribute(Qt.WA_TransparentForMouseEvents)

    if pixmap is not None and not pixmap.isNull():
        scaled = pixmap.scaled(THUMB_SIZE, THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(scaled)
        label.setFixedSize(scaled.size())
        label.setStyleSheet("border-radius: 6px;")
    else:
        label.setText("📄")
        label.setAlignment(Qt.AlignCenter)
        label.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        label.setStyleSheet(
            "font-size: 30px; background-color: rgba(30,30,30,220);"
            " border-radius: 8px; color: #fff;"
        )

    start_local = parent_widget.mapFromGlobal(start_global)
    end_local = parent_widget.mapFromGlobal(end_global)

    w, h = label.width(), label.height()
    start_rect = QRect(start_local.x() - w // 2, start_local.y() - h // 2, w, h)
    end_rect = QRect(end_local.x() - 6, end_local.y() - 6, 12, 12)

    label.setGeometry(start_rect)
    label.show()
    label.raise_()

    effect = QGraphicsOpacityEffect(label)
    label.setGraphicsEffect(effect)
    effect.setOpacity(1.0)

    geo_anim = QPropertyAnimation(label, b"geometry")
    geo_anim.setDuration(DURATION_MS)
    geo_anim.setStartValue(start_rect)
    geo_anim.setEndValue(end_rect)
    geo_anim.setEasingCurve(QEasingCurve.InCubic)

    fade_anim = QPropertyAnimation(effect, b"opacity")
    fade_anim.setDuration(DURATION_MS)
    fade_anim.setStartValue(1.0)
    fade_anim.setKeyValueAt(0.7, 0.9)
    fade_anim.setEndValue(0.0)
    fade_anim.setEasingCurve(QEasingCurve.InCubic)

    group = QParallelAnimationGroup(parent_widget)
    group.addAnimation(geo_anim)
    group.addAnimation(fade_anim)
    group.finished.connect(label.deleteLater)
    # riferimento tenuto sull'etichetta stessa, cosi' il gruppo non
    # viene raccolto dal garbage collector prima di finire
    label._fly_anim_group = group
    group.start()
