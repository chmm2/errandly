import uuid

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _reg_payload(**overrides) -> dict:
    email = f"verify_{uuid.uuid4().hex[:10]}@vitstudent.ac.in"
    payload = {
        "student_id": f"23BCE{uuid.uuid4().hex[:5]}",
        "email": email,
        "display_name": "Verify Me",
        "password": "password123",
    }
    payload.update(overrides)
    return payload


async def test_register_then_verify_activates_and_logs_in(client, campus):
    payload = _reg_payload()
    reg = await client.post("/auth/register", json=payload)
    assert reg.status_code == 201, reg.text
    assert reg.json()["account_status"] == "PENDING"
    # dev mode (no SMTP) hands the code back via the header
    otp = reg.headers.get("X-Dev-OTP")
    assert otp and len(otp) == 6

    # Can't log in yet — not verified
    denied = await client.post(
        "/auth/login", json={"email": payload["email"], "password": "password123"}
    )
    assert denied.status_code == 403

    # Wrong code is rejected
    bad = await client.post(
        "/auth/verify-email", json={"email": payload["email"], "code": "000000"}
    )
    assert bad.status_code == 400

    # Correct code → activates + returns tokens
    ok = await client.post(
        "/auth/verify-email", json={"email": payload["email"], "code": otp}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["access_token"]

    # And now normal login works
    login = await client.post(
        "/auth/login", json={"email": payload["email"], "password": "password123"}
    )
    assert login.status_code == 200


async def test_registration_rejects_non_campus_email(client, campus):
    reg = await client.post("/auth/register", json=_reg_payload(email="someone@gmail.com"))
    assert reg.status_code == 422
    assert "vitstudent.ac.in" in reg.json()["detail"]


async def test_resend_gives_a_fresh_code(client, campus):
    payload = _reg_payload()
    reg = await client.post("/auth/register", json=payload)
    first = reg.headers.get("X-Dev-OTP")

    resend = await client.post("/auth/resend-otp", json={"email": payload["email"]})
    assert resend.status_code == 202
    second = resend.headers.get("X-Dev-OTP")
    assert second and len(second) == 6

    # The old code no longer works; the new one does
    assert (
        await client.post(
            "/auth/verify-email", json={"email": payload["email"], "code": first}
        )
    ).status_code == 400
    assert (
        await client.post(
            "/auth/verify-email", json={"email": payload["email"], "code": second}
        )
    ).status_code == 200


async def test_resend_refused_once_verified(client, campus):
    payload = _reg_payload()
    reg = await client.post("/auth/register", json=payload)
    await client.post(
        "/auth/verify-email",
        json={"email": payload["email"], "code": reg.headers["X-Dev-OTP"]},
    )
    resend = await client.post("/auth/resend-otp", json={"email": payload["email"]})
    assert resend.status_code == 409
