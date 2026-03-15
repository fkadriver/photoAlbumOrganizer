"""Shared pytest configuration and fixtures."""
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--apple-limit",
        type=int,
        default=100,
        help="Number of photos to use in Apple integration tests (default: 100)",
    )


@pytest.fixture
def apple_limit(request):
    """Number of photos to use in Apple integration tests."""
    return request.config.getoption("--apple-limit")
