from email.message import EmailMessage
import smtplib
from logger import get_logger

logger = get_logger()

def send_report(bad_urls, config):
    if not bad_urls:
        logger.info("No broken URLs found — skipping email.")
        return

    html_rows = []
    for r in bad_urls:
        html_rows.append(f"""
        <tr>
            <td><a href="{r['url']}">{r['url']}</a></td>
            <td>{r['status']}</td>
            <td>{r['reason']}</td>
            <td>{r['link_type']}</td>
            <td>{r['element']}</td>
            <td>{r['anchor_text']}</td>
            <td><a href="{r['source_page']}">Source</a></td>
        </tr>
        """)

    html_table = f"""
    <html>
    <body style="font-family:Arial, sans-serif;">
      <p>⚠️ Detected {len(bad_urls)} problematic URLs:</p>
      <table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse;">
        <tr style="background:#f3f3f3;">
          <th>Broken URL</th><th>Status</th><th>Reason</th>
          <th>Type</th><th>Element</th><th>Anchor</th><th>Source Page</th>
        </tr>
        {''.join(html_rows)}
      </table>
      <p style="margin-top:20px;">Generated automatically by Strapi Monitor.</p>
    </body>
    </html>
    """

    msg = EmailMessage()
    msg["From"] = config["email"]["from"]
    msg["To"] = ", ".join(config["email"]["to"])
    msg["Subject"] = f"🚨 {len(bad_urls)} Broken URLs Detected on the website"
    msg.set_content("Please view this email in HTML format.")
    msg.add_alternative(html_table, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(config["email"]["from"], config["email"]["app_password"])
        smtp.send_message(msg)

    logger.info(f"📧 Detailed email sent with {len(bad_urls)} broken URLs.")
#evaturivamsikrishna