from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Final
from typing import cast

import numpy as np
import PIL.Image
from numpy.typing import NDArray

if TYPE_CHECKING:
    import pydicom as _pydicom_type

try:
    import pydicom
    from pydicom.multival import MultiValue
    from pydicom.pixels import apply_modality_lut
except ImportError:
    pydicom = None  # ty: ignore[invalid-assignment]
    MultiValue = ()  # ty: ignore[invalid-assignment]
    apply_modality_lut = None  # ty: ignore[invalid-assignment]

try:
    import SimpleITK as sitk
except ImportError:
    sitk = None  # ty: ignore[invalid-assignment]

DICOM_EXTENSIONS: Final[tuple[str, ...]] = (".dcm", ".dicom")

DICOM_WINDOW_PRESETS: Final[dict[str, tuple[float, float] | None]] = {
    "auto": None,
    "ct_brain": (40.0, 80.0),
    "ct_lung": (-600.0, 1500.0),
    "ct_soft_tissue": (40.0, 400.0),
    "ct_liver": (60.0, 160.0),
    "ct_bone": (400.0, 1800.0),
    "ct_stroke": (32.0, 8.0),
}

DICOM_PRESET_LABELS: Final[dict[str, str]] = {
    "auto": "Auto (Header / Percentile)",
    "ct_brain": "CT Brain (WL: 40, WW: 80)",
    "ct_lung": "CT Lung (WL: -600, WW: 1500)",
    "ct_soft_tissue": "CT Soft Tissue (WL: 40, WW: 400)",
    "ct_liver": "CT Liver (WL: 60, WW: 160)",
    "ct_bone": "CT Bone (WL: 400, WW: 1800)",
    "ct_stroke": "CT Stroke (WL: 32, WW: 8)",
    "custom": "Custom",
}

_MIN_WINDOW_WIDTH: Final[float] = 1.0
_UINT8_MAX_FLOAT: Final[float] = 255.0
_SPACING_LEN: Final[int] = 2


def is_dicom_file(*, filename: str | Path) -> bool:
    return Path(filename).suffix.lower() in DICOM_EXTENSIONS


def has_dicom_support() -> bool:
    return pydicom is not None


def _require_dicom_support() -> None:
    if pydicom is None:
        raise OSError(
            "Opening DICOM files requires optional dependencies. "
            "Install them with: pip install 'labelme[dicom]'"
        )


def _is_multi_value(*, value: object) -> bool:
    if isinstance(value, list | tuple):
        return True
    return bool(MultiValue) and isinstance(value, MultiValue)


def _first_float(*, value: object) -> float | None:
    if value is None:
        return None
    if _is_multi_value(value=value):
        seq = cast(list[object] | tuple[object, ...], value)
        if not seq:
            return None
        value = seq[0]
    try:
        return float(cast(float | str, value))
    except (TypeError, ValueError):
        return None


def _first_int(*, value: object) -> int | None:
    if value is None:
        return None
    if _is_multi_value(value=value):
        seq = cast(list[object] | tuple[object, ...], value)
        if not seq:
            return None
        value = seq[0]
    try:
        return int(cast(int | str, value))
    except (TypeError, ValueError):
        return None


def _first_str(*, value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _float_list(*, value: object, expected_len: int) -> list[float] | None:
    if value is None or not _is_multi_value(value=value):
        return None
    seq = cast(list[object] | tuple[object, ...], value)
    if len(seq) < expected_len:
        return None
    try:
        return [float(cast(float | str, seq[i])) for i in range(expected_len)]
    except (TypeError, ValueError):
        return None


def read_dicom_dimensions(*, filename: str | Path) -> tuple[int, int]:
    _require_dicom_support()
    assert pydicom is not None
    path_str = str(filename)
    try:
        ds = pydicom.dcmread(path_str, stop_before_pixels=True, force=True)
        rows = _first_int(value=getattr(ds, "Rows", None))
        cols = _first_int(value=getattr(ds, "Columns", None))
        if rows is not None and cols is not None and rows > 0 and cols > 0:
            return cols, rows
    except Exception:
        pass

    if sitk is not None:
        try:
            reader = sitk.ImageFileReader()
            reader.SetFileName(path_str)
            reader.ReadImageInformation()
            size = reader.GetSize()
            if len(size) >= _SPACING_LEN and size[0] > 0 and size[1] > 0:
                return int(size[0]), int(size[1])
        except Exception as e:
            raise OSError(
                f"Failed to read DICOM dimensions from {path_str!r}: {e}"
            ) from e

    raise OSError(f"Missing valid Rows/Columns in DICOM file: {path_str!r}")


def apply_dicom_window(
    *,
    hu_array: NDArray[np.float32],
    window_center: float,
    window_width: float,
    invert: bool = False,
) -> NDArray[np.uint8]:
    effective_width = max(float(window_width), _MIN_WINDOW_WIDTH)
    center = float(window_center)
    lower = center - effective_width / 2.0
    upper = center + effective_width / 2.0
    scaled = (hu_array.astype(np.float32) - lower) / (upper - lower) * _UINT8_MAX_FLOAT
    clipped = np.clip(
        np.nan_to_num(scaled, nan=0.0, posinf=_UINT8_MAX_FLOAT, neginf=0.0),
        0.0,
        _UINT8_MAX_FLOAT,
    )
    if invert:
        clipped = _UINT8_MAX_FLOAT - clipped
    return np.round(clipped).astype(np.uint8)


def compute_auto_window(
    *,
    hu_array: NDArray[np.float32],
    header_center: float | None = None,
    header_width: float | None = None,
) -> tuple[float, float]:
    PERCENTILE_LOW: Final[float] = 1.0
    PERCENTILE_HIGH: Final[float] = 99.0

    if (
        header_center is not None
        and header_width is not None
        and header_width >= _MIN_WINDOW_WIDTH
    ):
        return float(header_center), float(header_width)

    finite = hu_array[np.isfinite(hu_array)]
    if finite.size == 0:
        return 0.0, _UINT8_MAX_FLOAT

    p_low = float(np.percentile(finite, PERCENTILE_LOW))
    p_high = float(np.percentile(finite, PERCENTILE_HIGH))
    if p_high <= p_low:
        p_low = float(finite.min())
        p_high = float(finite.max())

    center = (p_low + p_high) / 2.0
    width = max(p_high - p_low, _MIN_WINDOW_WIDTH)
    return center, width


@dataclass
class DicomSessionData:
    hu_array: NDArray[np.float32]
    rgb_array: NDArray[np.uint8] | None
    modality: str | None
    photometric_interpretation: str
    window_center: float
    window_width: float
    is_inverted: bool
    preset_name: str
    metadata_dict: dict[str, Any]

    @property
    def header_window_center(self) -> float | None:
        radiometry = self.metadata_dict.get("radiometry", {})
        val = radiometry.get("headerWindowCenter")
        return float(val) if isinstance(val, int | float) else None

    @property
    def header_window_width(self) -> float | None:
        radiometry = self.metadata_dict.get("radiometry", {})
        val = radiometry.get("headerWindowWidth")
        return float(val) if isinstance(val, int | float) else None

    @property
    def rescale_type(self) -> str | None:
        radiometry = self.metadata_dict.get("radiometry", {})
        val = radiometry.get("rescaleType")
        return str(val) if isinstance(val, str) else None

    def default_auto_window(self) -> tuple[float, float]:
        return compute_auto_window(
            hu_array=self.hu_array,
            header_center=self.header_window_center,
            header_width=self.header_window_width,
        )

    def default_is_inverted(self) -> bool:
        return self.photometric_interpretation == "MONOCHROME1"

    def render_uint8(self) -> NDArray[np.uint8]:
        if self.rgb_array is not None:
            if self.is_inverted:
                return (_UINT8_MAX_FLOAT - self.rgb_array).astype(np.uint8)
            return self.rgb_array.copy()
        return apply_dicom_window(
            hu_array=self.hu_array,
            window_center=self.window_center,
            window_width=self.window_width,
            invert=self.is_inverted,
        )

    def render_pil(self) -> PIL.Image.Image:
        return PIL.Image.fromarray(self.render_uint8())

    def to_other_data(self) -> dict[str, Any]:
        data = copy.deepcopy(self.metadata_dict)
        data["viewState"] = {
            "appliedWindowCenter": float(self.window_center),
            "appliedWindowWidth": float(self.window_width),
            "appliedPresetName": str(self.preset_name),
            "isInverted": bool(self.is_inverted),
        }
        return data

    def apply_view_state(self, *, view_state: dict[str, Any]) -> None:
        wc = view_state.get("appliedWindowCenter")
        ww = view_state.get("appliedWindowWidth")
        preset = view_state.get("appliedPresetName")
        inverted = view_state.get("isInverted")
        if isinstance(wc, int | float) and not isinstance(wc, bool):
            self.window_center = float(wc)
        if isinstance(ww, int | float) and not isinstance(ww, bool):
            self.window_width = max(float(ww), _MIN_WINDOW_WIDTH)
        if isinstance(preset, str) and preset:
            self.preset_name = preset
        if isinstance(inverted, bool):
            self.is_inverted = inverted

    def format_intensity_at(self, *, x: float, y: float) -> str | None:
        height, width = self.hu_array.shape[:2]
        if height <= 0 or width <= 0:
            return None
        col = min(max(round(x), 0), width - 1)
        row = min(max(round(y), 0), height - 1)
        value = round(float(self.hu_array[row, col]))
        is_hu = self.modality == "CT" or self.rescale_type == "HU"
        prefix = "HU" if is_hu else "Val"
        return f"{prefix}: {value}"


DicomMetadata = DicomSessionData


def _extract_safe_metadata(
    *,
    ds: _pydicom_type.Dataset,
    window_center: float,
    window_width: float,
    preset_name: str,
    is_inverted: bool,
) -> dict[str, Any]:
    POSITION_LEN: Final[int] = 3
    ORIENTATION_LEN: Final[int] = 6

    # Strict Allowlist: only UIDs, spatial geometry, radiometry, and viewState.
    # Never reads PatientName, PatientID, PatientBirthDate, InstitutionName, etc.
    uids: dict[str, Any] = {
        "sopInstanceUid": _first_str(value=getattr(ds, "SOPInstanceUID", None)),
        "seriesInstanceUid": _first_str(value=getattr(ds, "SeriesInstanceUID", None)),
        "studyInstanceUid": _first_str(value=getattr(ds, "StudyInstanceUID", None)),
        "frameOfReferenceUid": _first_str(
            value=getattr(ds, "FrameOfReferenceUID", None)
        ),
        "instanceNumber": _first_int(value=getattr(ds, "InstanceNumber", None)),
    }

    pixel_spacing = _float_list(
        value=getattr(ds, "PixelSpacing", None), expected_len=_SPACING_LEN
    )
    if pixel_spacing is None:
        pixel_spacing = _float_list(
            value=getattr(ds, "ImagerPixelSpacing", None), expected_len=_SPACING_LEN
        )

    geometry: dict[str, Any] = {
        "pixelSpacingMm": pixel_spacing,
        "sliceThicknessMm": _first_float(value=getattr(ds, "SliceThickness", None)),
        "spacingBetweenSlicesMm": _first_float(
            value=getattr(ds, "SpacingBetweenSlices", None)
        ),
        "imagePositionPatient": _float_list(
            value=getattr(ds, "ImagePositionPatient", None),
            expected_len=POSITION_LEN,
        ),
        "imageOrientationPatient": _float_list(
            value=getattr(ds, "ImageOrientationPatient", None),
            expected_len=ORIENTATION_LEN,
        ),
    }

    rescale_slope = _first_float(value=getattr(ds, "RescaleSlope", None))
    rescale_intercept = _first_float(value=getattr(ds, "RescaleIntercept", None))

    radiometry: dict[str, Any] = {
        "modality": _first_str(value=getattr(ds, "Modality", None)),
        "photometricInterpretation": _first_str(
            value=getattr(ds, "PhotometricInterpretation", None)
        ),
        "bitsStored": _first_int(value=getattr(ds, "BitsStored", None)),
        "rescaleSlope": 1.0 if rescale_slope is None else rescale_slope,
        "rescaleIntercept": 0.0 if rescale_intercept is None else rescale_intercept,
        "rescaleType": _first_str(value=getattr(ds, "RescaleType", None)),
        "headerWindowCenter": _first_float(value=getattr(ds, "WindowCenter", None)),
        "headerWindowWidth": _first_float(value=getattr(ds, "WindowWidth", None)),
    }

    view_state: dict[str, Any] = {
        "appliedWindowCenter": float(window_center),
        "appliedWindowWidth": float(window_width),
        "appliedPresetName": str(preset_name),
        "isInverted": bool(is_inverted),
    }

    return {
        "uids": uids,
        "geometry": geometry,
        "radiometry": radiometry,
        "viewState": view_state,
    }


def _normalize_decoded_array(
    *, raw_arr: NDArray[Any], is_color: bool
) -> tuple[NDArray[np.float32], NDArray[np.uint8] | None]:
    NDIM_2D: Final[int] = 2
    NDIM_3D: Final[int] = 3
    NDIM_4D: Final[int] = 4
    RGB_CHANNELS: Final[int] = 3
    RGBA_CHANNELS: Final[int] = 4

    arr = raw_arr
    if arr.ndim == NDIM_4D:
        arr = arr[0]

    if arr.ndim == NDIM_3D:
        if is_color and arr.shape[2] in (RGB_CHANNELS, RGBA_CHANNELS):
            rgb = np.clip(arr[..., :RGB_CHANNELS], 0, 255).astype(np.uint8)
            hu = rgb.mean(axis=2).astype(np.float32)
            return hu, rgb
        arr = arr[0]

    if arr.ndim != NDIM_2D:
        raise OSError(f"Unsupported DICOM pixel array shape: {raw_arr.shape}")

    return arr.astype(np.float32), None


def _decode_with_pydicom(
    *, path_str: str, is_color: bool
) -> tuple[NDArray[np.float32], NDArray[np.uint8] | None]:
    _require_dicom_support()
    assert pydicom is not None and apply_modality_lut is not None
    ds_full = pydicom.dcmread(path_str, force=True)
    pixel_array = ds_full.pixel_array
    if is_color:
        return _normalize_decoded_array(raw_arr=pixel_array, is_color=True)
    modality_arr = apply_modality_lut(pixel_array, ds_full)
    return _normalize_decoded_array(raw_arr=np.asarray(modality_arr), is_color=False)


def _decode_with_sitk(
    *, path_str: str, is_color: bool
) -> tuple[NDArray[np.float32], NDArray[np.uint8] | None]:
    if sitk is None:
        raise OSError("SimpleITK is not installed")
    sitk_img = sitk.ReadImage(path_str)
    has_components = sitk_img.GetNumberOfComponentsPerPixel() > 1
    raw_arr = sitk.GetArrayFromImage(sitk_img)
    return _normalize_decoded_array(
        raw_arr=raw_arr, is_color=is_color or has_components
    )


def load_dicom_session(*, filename: str | Path) -> DicomSessionData:
    _require_dicom_support()
    assert pydicom is not None
    path_str = str(filename)
    try:
        ds_header = pydicom.dcmread(path_str, stop_before_pixels=True, force=True)
    except Exception as e:
        raise OSError(f"Failed to read DICOM header {path_str!r}: {e}") from e

    photometric = (
        _first_str(value=getattr(ds_header, "PhotometricInterpretation", None))
        or "MONOCHROME2"
    ).upper()
    modality = _first_str(value=getattr(ds_header, "Modality", None))
    is_color = photometric in ("RGB", "YBR_FULL", "YBR_FULL_422", "PALETTE COLOR")

    # SimpleITK's GDCM reader automatically inverts MONOCHROME1 pixel values
    # to ((1 << BitsStored) - 1 - pixel), which would conflict with explicit
    # VOI LUT windowing and MONOCHROME1 inversion. For MONOCHROME1, decode
    # stored/Modality-LUT values via pydicom first; for all other files, use
    # SimpleITK first (C++ GDCM/OpenJPEG + Modality LUT) with pydicom fallback.
    try:
        if photometric == "MONOCHROME1":
            hu_array, rgb_array = _decode_with_pydicom(
                path_str=path_str, is_color=is_color
            )
        else:
            hu_array, rgb_array = _decode_with_sitk(
                path_str=path_str, is_color=is_color
            )
    except Exception:
        try:
            if photometric == "MONOCHROME1":
                hu_array, rgb_array = _decode_with_sitk(
                    path_str=path_str, is_color=is_color
                )
            else:
                hu_array, rgb_array = _decode_with_pydicom(
                    path_str=path_str, is_color=is_color
                )
        except Exception as e:
            raise OSError(f"Failed to decode DICOM pixels {path_str!r}: {e}") from e

    header_wc = _first_float(value=getattr(ds_header, "WindowCenter", None))
    header_ww = _first_float(value=getattr(ds_header, "WindowWidth", None))
    window_center, window_width = compute_auto_window(
        hu_array=hu_array,
        header_center=header_wc,
        header_width=header_ww,
    )
    # Only MONOCHROME1 defaults to inverted; MONOCHROME2 is never auto-inverted.
    is_inverted = photometric == "MONOCHROME1"
    preset_name = "auto"

    metadata_dict = _extract_safe_metadata(
        ds=ds_header,
        window_center=window_center,
        window_width=window_width,
        preset_name=preset_name,
        is_inverted=is_inverted,
    )

    return DicomSessionData(
        hu_array=hu_array,
        rgb_array=rgb_array,
        modality=modality,
        photometric_interpretation=photometric,
        window_center=window_center,
        window_width=window_width,
        is_inverted=is_inverted,
        preset_name=preset_name,
        metadata_dict=metadata_dict,
    )


def imread_dicom(*, filename: str | Path) -> PIL.Image.Image:
    session = load_dicom_session(filename=filename)
    return session.render_pil()
