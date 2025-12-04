__version__ = "0.0.0"
version_split = __version__.split(".")
if len(version_split) < 3:
    raise ValueError(
        f"Version string '{__version__}' must be in format 'X.Y.Z' (e.g., '0.0.0')"
    )
try:
    __spec_version__ = (
        (1000 * int(version_split[0]))
        + (10 * int(version_split[1]))
        + (1 * int(version_split[2]))
    )
except (ValueError, IndexError) as e:
    raise ValueError(
        f"Invalid version string '{__version__}': {e}. "
        f"Version must be in format 'X.Y.Z' where X, Y, Z are integers."
    ) from e

# Import all submodules.
from . import protocol
from . import base
from . import validator
from . import api
