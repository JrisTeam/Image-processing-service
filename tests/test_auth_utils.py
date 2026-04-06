"""
Unit + property-based tests for app/auth/utils.py

Property 4: Passwords are never stored in plaintext
  Validates: Requirements 1.4

Property 5: Login round-trip returns a valid JWT
  Validates: Requirements 2.1, 2.3

Property 7: Tampered JWTs are always rejected
  Validates: Requirements 3.3
"""
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.auth.utils import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_hash_password_not_plaintext():
    h = hash_password("secret")
    assert h != "secret"
    assert h.startswith("$2b$")


def test_verify_password_correct():
    h = hash_password("mypassword")
    assert verify_password("mypassword", h) is True


def test_verify_password_wrong():
    h = hash_password("mypassword")
    assert verify_password("wrong", h) is False


def test_create_and_decode_token():
    uid = uuid.uuid4()
    token = create_access_token(uid)
    payload = decode_access_token(token)
    assert payload["sub"] == str(uid)


def test_decode_invalid_token_raises():
    with pytest.raises(Exception):
        decode_access_token("not.a.valid.token")


# ---------------------------------------------------------------------------
# Property 4: Passwords are never stored in plaintext
# Validates: Requirements 1.4
# ---------------------------------------------------------------------------

@given(password=st.text(min_size=1, max_size=72).filter(lambda p: len(p.encode()) <= 72))
@settings(max_examples=50, deadline=None)
def test_property_4_password_never_plaintext(password):
    """**Property 4: Passwords are never stored in plaintext**
    **Validates: Requirements 1.4**
    """
    hashed = hash_password(password)
    assert hashed != password
    assert hashed.startswith("$2b$")


# ---------------------------------------------------------------------------
# Property 5: Login round-trip returns a valid JWT
# Validates: Requirements 2.1, 2.3
# ---------------------------------------------------------------------------

@given(user_id=st.uuids())
@settings(max_examples=50)
def test_property_5_jwt_round_trip(user_id):
    """**Property 5: Login round-trip returns a valid JWT**
    **Validates: Requirements 2.1, 2.3**
    """
    token = create_access_token(user_id)
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    # exp - iat must be <= 86400 seconds (24 h)
    assert payload["exp"] - payload["iat"] <= 86400


# ---------------------------------------------------------------------------
# Property 7: Tampered JWTs are always rejected
# Validates: Requirements 3.3
# ---------------------------------------------------------------------------

@given(user_id=st.uuids(), mutation_index=st.integers(min_value=0, max_value=9))
@settings(max_examples=50)
def test_property_7_tampered_jwt_rejected(user_id, mutation_index):
    """**Property 7: Tampered JWTs are always rejected**
    **Validates: Requirements 3.3**
    """
    token = create_access_token(user_id)
    # Mutate a character in the signature (last segment)
    parts = token.split(".")
    sig = list(parts[2])
    idx = mutation_index % len(sig)
    # Flip one character to something different
    original = sig[idx]
    replacement = "A" if original != "A" else "B"
    sig[idx] = replacement
    tampered = ".".join(parts[:2] + ["".join(sig)])
    with pytest.raises(Exception):
        decode_access_token(tampered)
