"""OptimusPy — TM1 Cube Dimension Order Optimizer"""

__version__ = "2.0.0"

# Public API re-exports (preserves: from optimuspy import get_tm1_config, etc.)
from optimuspy.core import (
    APP_NAME,
    RESULT_PATH,
    get_tm1_config,
    load_cube_config,
    validate_cube_config,
    main,
    set_current_directory,
    configure_logging,
    _scan_to_data,
    _execute_scan_mode,
    _collect_dimension_metadata,
    _compute_suggested_order,
    _compute_nibble_depth,
)

__all__ = [
    "APP_NAME",
    "RESULT_PATH",
    "get_tm1_config",
    "load_cube_config",
    "validate_cube_config",
    "main",
    "set_current_directory",
    "configure_logging",
    "_scan_to_data",
    "_execute_scan_mode",
    "_collect_dimension_metadata",
    "_compute_suggested_order",
    "_compute_nibble_depth",
]
