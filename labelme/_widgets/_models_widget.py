from __future__ import annotations

import html
from collections.abc import Callable

import osam
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from .._ai_models import AI_TEXT_MODEL_OPTIONS
from .._ai_models import find_ai_assist_model_option
from .._model_manager import ModelManager


class ModelsWidget(QtWidgets.QWidget):
    def __init__(
        self, *, manager: ModelManager, remove_model: Callable[[str], None]
    ) -> None:
        super().__init__()
        self._manager = manager
        self._remove_model = remove_model
        self._links: dict[QtWidgets.QLabel, str] = {}
        self._rows: dict[
            str,
            tuple[
                QtWidgets.QLabel,
                QtWidgets.QPushButton,
                QtWidgets.QPushButton,
                QtWidgets.QPushButton,
            ],
        ] = {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(0)
        description = QtWidgets.QLabel(
            self.tr(
                "Download models to use AI offline. "
                "You can keep annotating while downloads run."
            )
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        recommendations = {
            "sam2:latest": self.tr(
                "Best balance of speed and quality for point and box prompts."
            ),
            "sam3:latest": self.tr(
                "Best for text prompts and finding multiple objects."
            ),
        }
        layout.addSpacing(12)
        heading = QtWidgets.QLabel(self.tr("Recommended"))
        heading_font = heading.font()
        heading_font.setBold(True)
        heading_font.setPointSizeF(heading_font.pointSizeF() * 1.15)
        heading.setFont(heading_font)
        layout.addWidget(heading)
        layout.addSpacing(4)
        all_models = [name for name in manager.models if name not in recommendations]
        for model_index, name in enumerate([*recommendations, *all_models]):
            if model_index == len(recommendations):
                layout.addSpacing(20)
                heading = QtWidgets.QLabel(self.tr("All models"))
                heading.setFont(heading_font)
                layout.addWidget(heading)
                layout.addSpacing(4)
            elif model_index:
                separator = QtWidgets.QFrame()
                separator.setFrameShape(QtWidgets.QFrame.Shape.HLine)
                layout.addWidget(separator)
            display = manager.models[name]
            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QGridLayout(row)
            row_layout.setContentsMargins(0, 12, 0, 12)
            title = QtWidgets.QLabel(display)
            font = title.font()
            font.setBold(True)
            title.setFont(font)
            row_layout.addWidget(title, 0, 0)
            if name in recommendations:
                reason = QtWidgets.QLabel(recommendations[name])
                reason.setWordWrap(True)
                row_layout.addWidget(reason, 1, 0, 1, 2)
            option = find_ai_assist_model_option(model_name=name)
            capabilities = []
            if option is not None:
                if option.supports_point_prompts:
                    capabilities.append(self.tr("Points"))
                capabilities.append(self.tr("Boxes"))
            if name in {model for model, _ in AI_TEXT_MODEL_OPTIONS}:
                capabilities.append(self.tr("Text prompts"))
            row_layout.addWidget(QtWidgets.QLabel(" · ".join(capabilities)), 2, 0, 1, 2)
            metadata = osam.apis.get_model_metadata(name)
            license_link = QtWidgets.QLabel(
                self.tr("License: {license}").format(
                    license=(
                        f'<a href="{html.escape(metadata.license_url, quote=True)}">'
                        f"{html.escape(metadata.license_name)}</a>"
                    ),
                )
            )
            license_link.setWordWrap(True)
            self._links[license_link] = license_link.text()
            license_link.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.LinksAccessibleByMouse
                | QtCore.Qt.TextInteractionFlag.LinksAccessibleByKeyboard
            )
            license_link.setOpenExternalLinks(True)
            row_layout.addWidget(license_link, 3, 0, 1, 2)
            if name == "sam3:latest":
                notice = QtWidgets.QLabel(
                    self.tr(
                        "SAM3 use is subject to the SAM License, including "
                        "trade-control and end-use restrictions. Read the full "
                        "agreement before downloading or using it."
                    )
                )
                notice.setWordWrap(True)
                row_layout.addWidget(notice, 4, 0, 1, 2)
            status = QtWidgets.QLabel()
            status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            status.setWordWrap(True)
            row_layout.addWidget(status, 5, 0, 1, 2)
            download = QtWidgets.QPushButton()
            download.clicked.connect(
                lambda _checked=False, model=name: self._download_or_cancel(model)
            )
            remove = QtWidgets.QPushButton(self.tr("Delete"))
            remove.setAccessibleName(self.tr("Delete {model}").format(model=display))
            remove.clicked.connect(
                lambda _checked=False, model=name: self._delete(model)
            )
            details = QtWidgets.QPushButton(self.tr("Details…"))
            details.setAccessibleName(f"{details.text()} {display}")
            details.clicked.connect(
                lambda _checked=False, model=name: self._show_error(model)
            )
            buttons = QtWidgets.QHBoxLayout()
            buttons.addWidget(download)
            buttons.addWidget(remove)
            buttons.addWidget(details)
            buttons.addStretch()
            row_layout.addLayout(buttons, 6, 0, 1, 2)
            layout.addWidget(row)
            self._rows[name] = status, download, remove, details
        manager.changed.connect(self.refresh)
        manager.progress_changed.connect(self._refresh_progress)
        self.refresh()
        self._sync_link_color()

    def changeEvent(self, event: QtCore.QEvent, /) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.PaletteChange:
            self._sync_link_color()

    def _sync_link_color(self) -> None:
        # Underlines identify links; the text color keeps them readable in both themes.
        color = self.palette().color(QtGui.QPalette.ColorRole.WindowText).name()
        for label, text in self._links.items():
            label.setText(text.replace("<a ", f'<a style="color: {color}" '))

    def refresh(self) -> None:
        manager = self._manager
        labels = {
            "missing": self.tr("Not downloaded"),
            "downloaded": self.tr("Downloaded"),
            "failed": self.tr("Failed"),
        }
        for name, (status, download, remove, details) in self._rows.items():
            state = manager.get_state(name)
            if state == "queued":
                text = self.tr("Queued · position {position}").format(
                    position=manager.queue.index(name) + 1
                )
            elif state == "downloading":
                text = self._describe_transfer()
            else:
                text = labels[state]
            details.setVisible(state == "failed")
            status.setText(text)
            download.setText(
                self.tr("Cancel")
                if state in {"queued", "downloading"}
                else self.tr("Retry")
                if state == "failed"
                else self.tr("Download")
            )
            download.setEnabled(state != "downloaded")
            download.setAccessibleName(f"{download.text()} {manager.models[name]}")
            remove.setEnabled(state == "downloaded")

    def _refresh_progress(self) -> None:
        # Progress arrives per chunk, so touch only the active row.
        if self._manager.active is not None:
            self._rows[self._manager.active][0].setText(self._describe_transfer())

    def _describe_transfer(self) -> str:
        filename, done, total = self._manager.progress
        if not filename:
            return self.tr("Downloading…")
        locale = self.locale()
        return self.tr("Downloading {filename} · {done} / {total}").format(
            filename=filename,
            done=locale.formattedDataSize(done, 1),
            total=locale.formattedDataSize(total, 1) if total is not None else "?",
        )

    def _download_or_cancel(self, model_name: str, /) -> None:
        if self._manager.get_state(model_name) in {"queued", "downloading"}:
            self._manager.cancel(model_name)
        else:
            self._manager.enqueue(model_name)

    def _show_error(self, model_name: str, /) -> None:
        message = QtWidgets.QMessageBox(self)
        message.setWindowTitle(self.tr("Failed"))
        message.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        message.setText(self._manager.models[model_name])
        message.setInformativeText(
            self.tr("Download failed. Check your connection and retry.")
        )
        message.setDetailedText(self._manager.errors.get(model_name, ""))
        message.exec()

    def _delete(self, model_name: str, /) -> None:
        answer = QtWidgets.QMessageBox.question(
            self,
            self.tr("Delete model"),
            self.tr(
                "Delete {model} from this computer? Its selections will be cleared. "
                "Your annotations will not change."
            ).format(model=self._manager.models[model_name]),
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            try:
                self._remove_model(model_name)
            except OSError as error:
                QtWidgets.QMessageBox.warning(self, self.tr("Delete model"), str(error))
