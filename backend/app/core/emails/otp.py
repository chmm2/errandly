"""The verification-code email.

Inline styles and a table layout on purpose — mail clients strip <style>
blocks and have no useful flexbox support, so this is the one place in the
codebase where 2004-era HTML is the correct answer.

Colours track the app's brand tokens (frontend/src/index.css).
"""

BRAND = "#FC8019"
BRAND_DARK = "#E8720C"
INK = "#282C3F"
MUTED = "#686B78"
LINE = "#E9E9EB"


def otp_email(display_name: str, code: str, ttl_minutes: int) -> tuple[str, str]:
    """Return (plain_text, html) for a verification email.

    Both parts are sent: clients that refuse HTML still get a usable message,
    and spam filters treat multipart mail more kindly than HTML alone.
    """
    first = (display_name or "there").split(" ")[0]

    text = (
        f"Hi {first},\n\n"
        f"Your Errandly verification code is: {code}\n\n"
        f"It expires in {ttl_minutes} minutes.\n\n"
        "If you didn't sign up for Errandly, you can ignore this email.\n\n"
        "— Errandly · built by students, for students"
    )

    # Letter-spaced digits in a single cell; some clients drop letter-spacing,
    # so the size and weight carry it even when the tracking is ignored.
    html = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F4F5F6;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F4F5F6;padding:32px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="max-width:520px;background:#FFFFFF;border-radius:16px;overflow:hidden;
                    border:1px solid {LINE};font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">

        <!-- Brand band -->
        <tr>
          <td style="background:{BRAND};background-image:linear-gradient(135deg,{BRAND},{BRAND_DARK});
                     padding:28px 32px;">
            <span style="font-size:26px;vertical-align:middle;">&#128757;</span>
            <span style="color:#FFFFFF;font-size:24px;font-weight:800;letter-spacing:-0.5px;
                         vertical-align:middle;margin-left:6px;">errandly</span>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:32px;">
            <p style="margin:0 0 6px;color:{INK};font-size:20px;font-weight:700;">Hi {first},</p>
            <p style="margin:0 0 24px;color:{MUTED};font-size:15px;line-height:22px;">
              Use this code to verify your email and finish setting up your Errandly account.
            </p>

            <!-- Code -->
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                   style="background:#FFF4EA;border:1px solid #FFD9B8;border-radius:12px;">
              <tr>
                <td align="center" style="padding:22px 12px;">
                  <div style="color:{BRAND_DARK};font-size:34px;font-weight:800;
                              letter-spacing:10px;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
                    {code}
                  </div>
                  <div style="margin-top:8px;color:{MUTED};font-size:12px;letter-spacing:1px;
                              text-transform:uppercase;">
                    expires in {ttl_minutes} minutes
                  </div>
                </td>
              </tr>
            </table>

            <p style="margin:24px 0 0;color:{MUTED};font-size:13px;line-height:20px;">
              If you didn't sign up for Errandly, you can safely ignore this email &mdash;
              nothing will happen to your address.
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="border-top:1px solid {LINE};padding:18px 32px;">
            <p style="margin:0;color:{MUTED};font-size:12px;">
              errandly &middot; built by students, for students &middot; VIT Vellore
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return text, html
