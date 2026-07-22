import pytest
from pydantic import ValidationError

from app.config import Settings


def test_lifecycle_day_seconds_defaults_to_real_day() -> None:
    settings = Settings(_env_file=None)

    assert settings.lifecycle_day_seconds == 86_400


def test_lifecycle_day_seconds_accepts_positive_custom_value() -> None:
    settings = Settings(
        _env_file=None,
        lifecycle_day_seconds=60,
    )

    assert settings.lifecycle_day_seconds == 60


@pytest.mark.parametrize("value", [0, -1])
def test_lifecycle_day_seconds_must_be_positive(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            lifecycle_day_seconds=value,
        )
