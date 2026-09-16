from __future__ import annotations

import html
from collections.abc import Callable

import osam
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
        self._rows: dict[
            str, tuple[QtWidgets.QLabel, QtWidgets.QPushButton, QtWidgets.QPushButton]
        ] = {}
        layout = QtWidgets.QVBoxLayout(self)
        description = QtWidgets.QLabel(
            self.tr(
                "Download models to use AI offline. "
                "You can keep annotating while downloads run."
            )
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        for name, display in manager.models.items():
            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QGridLayout(row)
            row_layout.setContentsMargins(0, 12, 0, 12)
            title = QtWidgets.QLabel(display)
            font = title.font()
            font.setBold(True)
            title.setFont(font)
            row_layout.addWidget(title, 0, 0)
            option = find_ai_assist_model_option(model_name=name)
            capabilities = []
            if option is not None:
                if option.supports_point_prompts:
                    capabilities.append(self.tr("Points"))
                capabilities.append(self.tr("Boxes"))
            if name in {model for model, _ in AI_TEXT_MODEL_OPTIONS}:
                capabilities.append(self.tr("Text prompts"))
            row_layout.addWidget(QtWidgets.QLabel(" · ".join(capabilities)), 1, 0, 1, 2)
            metadata = osam.apis.get_model_metadata(name)
            license_link = QtWidgets.QLabel(
                self.tr(
                    'License: {license} · <a href="{source}">Model details</a>'
                ).format(
                    license=html.escape(metadata.license_name),
                    source=html.escape(metadata.source_url, quote=True),
                )
            )
            license_link.setWordWrap(True)
            license_link.setOpenExternalLinks(True)
            row_layout.addWidget(license_link, 2, 0, 1, 2)
            if name == "sam3:latest":
                notice = QtWidgets.QLabel(
                    self.tr(
                        "SAM3 use is subject to the SAM License, including "
                        "trade-control and end-use restrictions. Read the full "
                        "agreement before downloading or using it."
                    )
                )
                notice.setWordWrap(True)
                row_layout.addWidget(notice, 3, 0, 1, 2)
            status = QtWidgets.QLabel()
            status.setWordWrap(True)
            row_layout.addWidget(status, 4, 0, 1, 2)
            download = QtWidgets.QPushButton()
            download.setAccessibleName(
                self.tr("Download or cancel {model}").format(model=display)
            )
            download.clicked.connect(
                lambda _checked=False, model=name: self._download_or_cancel(model)
            )
            remove = QtWidgets.QPushButton(self.tr("Delete"))
            remove.setAccessibleName(self.tr("Delete {model}").format(model=display))
            remove.clicked.connect(
                lambda _checked=False, model=name: self._delete(model)
            )
            buttons = QtWidgets.QHBoxLayout()
            buttons.addWidget(download)
            buttons.addWidget(remove)
            buttons.addStretch()
            row_layout.addLayout(buttons, 5, 0, 1, 2)
            layout.addWidget(row)
            self._rows[name] = status, download, remove
        manager.changed.connect(self.refresh)
        manager.progress_changed.connect(self._refresh_progress)
        self.refresh()

    def refresh(self) -> None:
        manager = self._manager
        labels = {
            "missing": self.tr("Not downloaded"),
            "downloaded": self.tr("Downloaded"),
            "failed": self.tr("Failed"),
        }
        for name, (status, download, remove) in self._rows.items():
            state = manager.get_state(name)
            if state == "queued":
                text = self.tr("Queued · position {position}").format(
                    position=manager.queue.index(name) + 1
                )
            elif state == "downloading":
                text = self._describe_transfer()
            else:
                text = labels[state]
            if state == "failed":
                text += ": " + manager.errors.get(name, "")
            status.setText(text)
            download.setText(
                self.tr("Cancel")
                if state in {"queued", "downloading"}
                else self.tr("Retry")
                if state == "failed"
                else self.tr("Download")
            )
            download.setEnabled(state != "downloaded")
            remove.setEnabled(state == "downloaded")

    def _refresh_progress(self) -> None:
        # Progress arrives per chunk, so touch only the active row.
        if self._manager.active is not None:
            self._rows[self._manager.active][0].setText(self._describe_transfer())

    def _describe_transfer(self) -> str:
        filename, done, total = self._manager.progress
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

    def _delete(self, model_name: str, /) -> None:
        answer = QtWidgets.QMessageBox.question(
            self,
            self.tr("Delete model"),
            self.tr(
                "Delete {model} from this computer? Its selections will be cleared. "
                "Your annotations will not change."
            ).format(model=self._manager.models[model_name]),
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            try:
                self._remove_model(model_name)
            except OSError as error:
                QtWidgets.QMessageBox.warning(self, self.tr("Delete model"), str(error))
