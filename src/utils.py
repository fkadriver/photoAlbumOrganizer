"""
Utility functions and classes for photo organizer.
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime


class SuppressStderr:
    """Context manager to suppress stderr at OS level (for LAPACK/BLAS warnings)."""

    def __enter__(self):
        # Save the original stderr file descriptor
        self._original_stderr_fd = os.dup(2)
        # Open /dev/null
        self._devnull = os.open(os.devnull, os.O_WRONLY)
        # Redirect stderr (fd 2) to /dev/null
        os.dup2(self._devnull, 2)
        # Also redirect Python's sys.stderr
        self._original_stderr = sys.stderr
        sys.stderr = open(os.devnull, 'w')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore stderr file descriptor
        os.dup2(self._original_stderr_fd, 2)
        os.close(self._original_stderr_fd)
        os.close(self._devnull)
        # Restore Python's sys.stderr
        sys.stderr.close()
        sys.stderr = self._original_stderr


def setup_logging(output_dir=None, verbose=False):
    """
    Setup logging to both file and console.

    Args:
        output_dir: Directory for log file (default: ~/.cache/photo-organizer/logs)
        verbose: Enable verbose debug logging

    Returns:
        Path to log file
    """
    # Determine log directory
    if output_dir:
        log_dir = Path(output_dir)
    else:
        log_dir = Path.home() / '.cache' / 'photo-organizer' / 'logs'

    log_dir.mkdir(parents=True, exist_ok=True)

    # Create log filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'photo_organizer_{timestamp}.log'

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler - always detailed
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console handler - only warnings and errors by default
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)

    # Root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Log startup
    logging.info("="*60)
    logging.info("Photo Organizer Started")
    logging.info(f"Log file: {log_file}")
    logging.info("="*60)

    return log_file
