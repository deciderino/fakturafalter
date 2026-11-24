# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Farben und Stylesheet (hell/dunkel), schlicht und kontrastreich. Klickziele mindestens 48 px, keine Animationen."""

from __future__ import annotations

ZIEL_PX = 48  # Mindesthöhe für Knöpfe/Reiter/Kästchen (44 px + 2 x 2 px Rahmen)


def farben(hell: bool) -> dict[str, str]:
    if hell:
        return dict(
            win="#f5f5f5",
            fg="#222222",
            card="#ffffff",
            card_b="#dcdcdc",
            sub="#666666",
            pill="#e8e8e8",
            pill_t="#555555",
            btn="#e0e0e0",
            btn_b="#cccccc",
            btn_h="#d0d0d0",
            base="#ffffff",
            acc="#1565c0",
            prim="#1565c0",
            prim_b="#0d47a1",
            ok="#43a047",
            off="#9e9e9e",
            busy="#ffb300",
            err="#e53935",
            dis_bg="#ececec",
            dis_fg="#a6a6a6",
            dis_b="#dddddd",
            bar="#ececec",
            bar_b="#d0d0d0",
            bar_t="#555555",
            ok_bg="#e8f5e9",
            ok_t="#1b5e20",
            er_bg="#ffebee",
            er_t="#b71c1c",
            in_bg="#fff8e1",
            in_t="#5d4037",
            log="#ffffff",
            warn_t="#c43e00",
            danger="#c62828",
            danger_b="#8e0000",
            sec="#555555",
            sel="#bbdefb",
        )
    return dict(
        win="#1e1e1e",
        fg="#e0e0e0",
        card="#262626",
        card_b="#303030",
        sub="#9a9a9a",
        pill="#333333",
        pill_t="#bbbbbb",
        btn="#2d2d2d",
        btn_b="#444444",
        btn_h="#3d3d3d",
        base="#2a2a2a",
        acc="#4fc3f7",
        prim="#1f5f8b",
        prim_b="#2a7ab0",
        ok="#43a047",
        off="#757575",
        busy="#ffb300",
        err="#e53935",
        dis_bg="#242424",
        dis_fg="#5c5c5c",
        dis_b="#323232",
        bar="#252525",
        bar_b="#333333",
        bar_t="#aaaaaa",
        ok_bg="#2e3b2f",
        ok_t="#e6e6e6",
        er_bg="#3b2a2a",
        er_t="#e6e6e6",
        in_bg="#3a3424",
        in_t="#e6e6e6",
        log="#1a1a1a",
        warn_t="#ffb74d",
        danger="#b3261e",
        danger_b="#e53935",
        sec="#bbbbbb",
        sel="#1f4f6f",
    )


def css(c: dict[str, str]) -> str:
    return f"""
    QWidget {{ font-size: 15px; color: {c["fg"]}; }}
    QMainWindow, QWidget#wurzel, QDialog, QScrollArea, QScrollArea > QWidget > QWidget#wurzel {{ background: {c["win"]}; }}
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{ background: {c["win"]}; width: 12px; margin: 0; border: none; }}
    QScrollBar::handle:vertical {{ background: {c["btn_b"]}; min-height: 48px; border-radius: 5px; margin: 2px; }}
    QScrollBar:horizontal {{ background: {c["win"]}; height: 12px; margin: 0; border: none; }}
    QScrollBar::handle:horizontal {{ background: {c["btn_b"]}; min-width: 48px; border-radius: 5px; margin: 2px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
    QLabel {{ background: transparent; }}
    QFrame#karte {{ background: {c["card"]}; border: 1px solid {c["card_b"]}; border-radius: 6px; }}
    QFrame#leiste {{ background: {c["win"]}; border-bottom: 1px solid {c["bar_b"]}; }}
    QLabel#titel {{ font-size: 17px; font-weight: bold; }}
    QLabel#gross {{ font-size: 24px; font-weight: bold; }}
    QLabel#sub {{ color: {c["sub"]}; font-size: 13px; }}
    QLabel#warn {{ color: {c["warn_t"]}; font-size: 13px; }}
    QLabel#gut {{ color: {c["ok"]}; font-size: 13px; }}
    QLabel#pille {{ background: {c["pill"]}; color: {c["pill_t"]}; border-radius: 9px; padding: 2px 10px; font-size: 13px; }}
    QLabel#sektion {{ font-size: 13px; font-weight: bold; color: {c["sec"]}; padding-top: 6px; }}
    QLabel#hinweis {{ color: {c["sub"]}; font-size: 13px; }}
    QLabel:disabled, QLabel#hinweis:disabled {{ color: {c["dis_fg"]}; }}
    QPushButton {{ background: {c["btn"]}; border: 2px solid {c["btn_b"]}; border-radius: 6px;
                   min-height: 44px; padding: 0px 14px; }}
    QPushButton:hover {{ background: {c["btn_h"]}; }}
    QPushButton:focus {{ border-color: {c["acc"]}; }}
    QPushButton#icon {{ min-width: 44px; max-width: 44px; font-size: 20px; padding: 0; }}
    QPushButton#klapp {{ background: transparent; border: none; color: {c["sub"]}; text-align: left; padding: 0 4px; min-height: 48px; }}
    QPushButton#klapp:focus {{ color: {c["acc"]}; }}
    QPushButton[primary="true"] {{ background: {c["prim"]}; color: #ffffff; border: 2px solid {c["prim_b"]}; }}
    QPushButton[danger="true"] {{ background: {c["danger"]}; color: #ffffff; border: 2px solid {c["danger_b"]}; }}
    QPushButton:disabled, QPushButton[primary="true"]:disabled, QPushButton[danger="true"]:disabled {{
                   background: {c["dis_bg"]}; color: {c["dis_fg"]}; border: 2px solid {c["dis_b"]}; }}
    QLineEdit, QSpinBox, QComboBox {{ background: {c["base"]}; border: 2px solid {c["btn_b"]}; border-radius: 4px;
                   min-height: 44px; padding: 0px 8px; }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {c["acc"]}; }}
    QComboBox QAbstractItemView {{ background: {c["base"]}; selection-background-color: {c["sel"]}; }}
    QComboBox QAbstractItemView::item {{ min-height: 44px; }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ background: {c["dis_bg"]}; color: {c["dis_fg"]}; border-color: {c["dis_b"]}; }}
    QCheckBox, QRadioButton {{ spacing: 12px; min-height: 48px; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 26px; height: 26px; }}
    QCheckBox::indicator {{ border: 1px solid {c["off"]}; border-radius: 3px; background: {c["base"]}; }}
    QCheckBox::indicator:checked {{ background: #4caf50; border-color: #388e3c; }}
    QCheckBox::indicator:disabled {{ background: {c["dis_bg"]}; border-color: {c["dis_b"]}; }}
    QCheckBox:disabled, QRadioButton:disabled {{ color: {c["dis_fg"]}; }}
    QTextEdit, QPlainTextEdit {{ background: {c["log"]}; border: 1px solid {c["card_b"]}; font-family: "Liberation Mono"; font-size: 14px; }}
    QStatusBar {{ background: {c["bar"]}; border-top: 1px solid {c["bar_b"]}; }}
    QStatusBar QLabel {{ color: {c["bar_t"]}; font-size: 13px; padding: 0 10px; }}
    QStatusBar QLabel:disabled {{ color: {c["dis_fg"]}; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ min-height: 48px; padding: 0 18px; background: {c["btn"]}; border: 1px solid {c["btn_b"]};
                    border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 4px; }}
    QTabBar::tab:selected {{ background: {c["card"]}; border-color: {c["acc"]}; font-weight: bold; }}
    QFrame#trenner {{ background: {c["card_b"]}; max-height: 1px; min-height: 1px; }}
    QMenu {{ background: {c["card"]}; border: 1px solid {c["card_b"]}; }}
    QMenu::item {{ padding: 14px 24px; min-height: 20px; }}
    QMenu::item:selected {{ background: {c["sel"]}; }}
    QMenu::item:disabled {{ color: {c["dis_fg"]}; }}
    QToolTip {{ background: {c["card"]}; color: {c["fg"]}; border: 1px solid {c["card_b"]}; }}
    """


def ist_hell(einstellung: str) -> bool:
    """einstellung: 'hell' | 'dunkel' | 'system'."""
    if einstellung in ("hell", "dunkel"):
        return einstellung == "hell"
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication

        return QGuiApplication.styleHints().colorScheme() != Qt.ColorScheme.Dark
    except Exception:  # noqa: BLE001 – ältere Qt-Versionen / offscreen
        return True


def anwenden(app, einstellung: str) -> dict[str, str]:
    c = farben(ist_hell(einstellung))
    app.setStyleSheet(css(c))
    return c
