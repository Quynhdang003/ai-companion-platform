"""Phone number normalization at the system boundary (web forms, pre-call hook)."""

import phonenumbers
from phonenumbers import PhoneNumberFormat, PhoneNumberType

# Numbers an elder can call from; excludes toll-free, premium and other service ranges.
_CALLER_TYPES = {
    PhoneNumberType.MOBILE,
    PhoneNumberType.FIXED_LINE,
    PhoneNumberType.FIXED_LINE_OR_MOBILE,
}


class InvalidPhoneError(ValueError):
    pass


def normalize_vn_phone(raw: str) -> str:
    """E.164 form of a Vietnamese mobile or landline number in any common notation.

    `0912 345 678`, `0912.345.678`, `84912345678` and `+84912345678` all give `+84912345678`.
    """
    try:
        number = phonenumbers.parse(raw, "VN")
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneError(raw) from exc
    if (
        not phonenumbers.is_valid_number(number)
        or phonenumbers.region_code_for_number(number) != "VN"
        or phonenumbers.number_type(number) not in _CALLER_TYPES
    ):
        raise InvalidPhoneError(raw)
    return phonenumbers.format_number(number, PhoneNumberFormat.E164)
