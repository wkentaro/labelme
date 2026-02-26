import importlib.metadata
import logging
import sys

__appname__ = "Labelme"

# Semantic Versioning 2.0.0: https://semver.org/
# 1. MAJOR version when you make incompatible API changes;
# 2. MINOR version when you add functionality in a backwards-compatible manner;
# 3. PATCH version when you make backwards-compatible bug fixes.
# e.g., 1.0.0a0, 1.0.0a1, 1.0.0b0, 1.0.0rc0, 1.0.0, 1.0.0.post0
__version__ = importlib.metadata.version("labelme")

# XXX: has to be imported before PyQt5 to load dlls in order on Windows
# https://github.com/wkentaro/labelme/issues/1564
# Make onnxruntime import optional to handle DLL loading failures gracefully
_ONNXRUNTIME_AVAILABLE = False
try:
    import onnxruntime
    _ONNXRUNTIME_AVAILABLE = True
except (ImportError, OSError, RuntimeError) as e:
    # Catch ImportError, OSError (DLL load failures), and RuntimeError
    # Log warning but don't fail - AI features will be disabled
    if sys.platform == "win32":
        import warnings
        warnings.warn(
            f"Failed to import onnxruntime: {e}\n"
            "AI-assisted annotation features will be disabled.\n"
            "To fix this issue, please ensure:\n"
            "1. Visual C++ Redistributable is installed\n"
            "   Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe\n"
            "2. All required DLL dependencies are available\n"
            "3. onnxruntime is properly installed for your Python version\n"
            "   Try: pip install --upgrade onnxruntime",
            ImportWarning,
            stacklevel=2,
        )
    else:
        # On non-Windows, this is less critical but still log it
        import warnings
        warnings.warn(
            f"Failed to import onnxruntime: {e}\n"
            "AI-assisted annotation features will be disabled.",
            ImportWarning,
            stacklevel=2,
        )

from labelme import testing
from labelme import utils
from labelme._label_file import LabelFile
