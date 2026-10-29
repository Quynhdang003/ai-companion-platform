import pytest

from app.services.identity.phone import InvalidPhoneError, normalize_vn_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0912345678", "+84912345678"),
        ("0912 345 678", "+84912345678"),
        ("0912.345.678", "+84912345678"),
        ("0912-345-678", "+84912345678"),
        ("84912345678", "+84912345678"),
        ("+84912345678", "+84912345678"),
        ("+84 912 345 678", "+84912345678"),
        ("0312345678", "+84312345678"),
        ("024 3826 1234", "+842438261234"),
        ("028 3822 1234", "+842838221234"),
    ],
)
def test_valid_numbers_normalize_to_e164(raw: str, expected: str) -> None:
    assert normalize_vn_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "abc",
        "091234",
        "09123456789012",
        "0212345678",
        "1900 1234",
        "1800 1234",
        "+1 650 253 0000",
    ],
    ids=["empty", "letters", "too-short", "too-long", "bad-prefix", "premium", "toll-free", "us"],
)
def test_invalid_numbers_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidPhoneError):
        normalize_vn_phone(raw)
