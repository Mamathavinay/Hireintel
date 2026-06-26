import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import EMAIL_SENDER, EMAIL_PASSWORD, SMTP_HOST, SMTP_PORT, COMPANY_NAME


def _send(to: str, subject: str, html: str) -> dict:
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        return {"success": False, "error": "Email credentials not set in .env"}
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{COMPANY_NAME} Talent Team <{EMAIL_SENDER}>"
        msg["To"] = to
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.sendmail(EMAIL_SENDER, to, msg.as_string())
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _hdr(color, title, sub=""):
    return f'<div style="background:{color};padding:22px 30px;border-radius:10px 10px 0 0"><h2 style="color:#fff;margin:0">{title}</h2>{"<p style=color:#ddd;margin:4px_0_0>"+sub+"</p>" if sub else ""}</div>'


def _footer():
    return f'<div style="background:#f5f5f5;padding:12px 30px;border-radius:0 0 10px 10px;font-size:11px;color:#aaa;text-align:center">Powered by HireIntel AI · {COMPANY_NAME}</div>'


def send_interview_invite(to, name, role, slots, jd_summary=""):
    opts = "".join(
        f"<div style='margin:6px 0;padding:10px 16px;background:#f3f0ff;border-left:4px solid #7F77DD;border-radius:4px'><strong>Option {i+1}:</strong> {s}</div>"
        for i, s in enumerate(slots)
    )
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
<div style="background:#7F77DD;padding:22px 30px;border-radius:10px 10px 0 0"><h2 style="color:#fff;margin:0">Interview Invitation</h2><p style="color:#ddd;margin:4px 0 0">{COMPANY_NAME}</p></div>
<div style="padding:26px 30px;background:#fff;border:1px solid #eee">
<p>Dear <strong>{name}</strong>,</p>
<p>Congratulations! Your profile has been <strong>shortlisted</strong> for <strong>{role}</strong> at {COMPANY_NAME}.</p>
{'<p style="color:#555;font-size:14px">'+jd_summary+'</p>' if jd_summary else ""}
<p>Please reply with your preferred interview slot:</p>{opts}
<p style="margin-top:18px">Kindly confirm within <strong>24 hours</strong>.</p>
<p>Warm regards,<br><strong>{COMPANY_NAME} Talent Team</strong></p>
</div><div style="background:#f5f5f5;padding:12px 30px;border-radius:0 0 10px 10px;font-size:11px;color:#aaa;text-align:center">Powered by HireIntel AI</div></div>"""
    return _send(to, f"Interview Invitation – {role} | {COMPANY_NAME}", html)


def send_confirmation(to, name, role, slot, panel=None, link=""):
    extra = ""
    if panel:
        extra += f"<p><strong>Panel:</strong> {', '.join(panel)}</p>"
    if link:
        extra += f'<p><strong>Link:</strong> <a href="{link}">{link}</a></p>'
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
<div style="background:#1D9E75;padding:22px 30px;border-radius:10px 10px 0 0"><h2 style="color:#fff;margin:0">Interview Confirmed ✓</h2><p style="color:#ddd;margin:4px 0 0">{COMPANY_NAME}</p></div>
<div style="padding:26px 30px;background:#fff;border:1px solid #eee">
<p>Dear <strong>{name}</strong>,</p>
<p>Your interview for <strong>{role}</strong> is <span style="color:#1D9E75;font-weight:bold">confirmed</span>.</p>
<div style="background:#f0fdf4;border-left:4px solid #1D9E75;padding:14px;border-radius:4px;margin:16px 0">
<p><strong>Date &amp; Time:</strong> {slot}</p><p><strong>Role:</strong> {role}</p>{extra}</div>
<p><strong>Preparation tips:</strong></p><ul><li>Join 5 minutes early</li><li>Keep resume ready</li><li>Stable internet connection</li></ul>
<p>Best of luck!</p><p>Warm regards,<br><strong>{COMPANY_NAME} Talent Team</strong></p>
</div><div style="background:#f5f5f5;padding:12px 30px;border-radius:0 0 10px 10px;font-size:11px;color:#aaa;text-align:center">Powered by HireIntel AI</div></div>"""
    return _send(to, f"Interview Confirmed – {slot} | {COMPANY_NAME}", html)


def send_rejection(to, name, role, feedback=""):
    fb = f'<div style="background:#fff8f0;border-left:4px solid #EF9F27;padding:12px 16px;border-radius:4px;margin:14px 0;font-size:14px"><strong>Feedback:</strong> {feedback}</div>' if feedback else ""
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
<div style="background:#888780;padding:22px 30px;border-radius:10px 10px 0 0"><h2 style="color:#fff;margin:0">Application Update</h2><p style="color:#ddd;margin:4px 0 0">{COMPANY_NAME}</p></div>
<div style="padding:26px 30px;background:#fff;border:1px solid #eee">
<p>Dear <strong>{name}</strong>,</p>
<p>Thank you for your interest in <strong>{role}</strong> at {COMPANY_NAME}.</p>
<p>After careful review, we will not be moving forward at this time.</p>{fb}
<p>We will keep your profile for future opportunities.</p>
<p>Warm regards,<br><strong>{COMPANY_NAME} Talent Team</strong></p>
</div><div style="background:#f5f5f5;padding:12px 30px;border-radius:0 0 10px 10px;font-size:11px;color:#aaa;text-align:center">Powered by HireIntel AI</div></div>"""
    return _send(to, f"Application Update – {role} | {COMPANY_NAME}", html)
