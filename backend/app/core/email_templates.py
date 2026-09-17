"""HTML templates for the emails sent via app/core/email.py::send_email.

Each `*_email()` function returns `(subject, text, html)` — the text version
is what already existed before Brevo/HTML support; the HTML version reuses
the same wording, wrapped in `_layout()` so every email shares one look
(brand colors lifted from frontend/app/theme/daylight.ts: primary blue
#0A66F5, background #F3F4F6).
"""

BRAND_NAME = "Marketplace Guinée"
COLOR_PRIMARY = "#0A66F5"
COLOR_BACKGROUND = "#F3F4F6"
COLOR_CARD = "#FFFFFF"
COLOR_TEXT = "#14151A"
COLOR_MUTED = "#6E7079"
COLOR_CODE_BG = "#EAF1FE"


def _layout(*, preheader: str, title: str, body_html: str) -> str:
    """Shared header/card/footer chrome. `body_html` is the email-specific content."""
    return f"""\
<!DOCTYPE html>
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
  </head>
  <body style="margin:0; padding:0; background-color:{COLOR_BACKGROUND}; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
    <div style="display:none; max-height:0; overflow:hidden; opacity:0;">{preheader}</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{COLOR_BACKGROUND}; padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px; width:100%;">
            <tr>
              <td style="padding:0 8px 20px;">
                <span style="font-size:18px; font-weight:700; color:{COLOR_PRIMARY};">{BRAND_NAME}</span>
              </td>
            </tr>
            <tr>
              <td style="background-color:{COLOR_CARD}; border-radius:12px; padding:32px; box-shadow:0 1px 3px rgba(20,21,26,0.08);">
                {body_html}
              </td>
            </tr>
            <tr>
              <td style="padding:20px 8px 0;">
                <p style="margin:0; font-size:12px; line-height:18px; color:{COLOR_MUTED};">
                  Cet email a été envoyé automatiquement, merci de ne pas y répondre.<br />
                  {BRAND_NAME} — netmarket.ndjouri.com
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def _code_block(code: str) -> str:
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;">
  <tr>
    <td align="center" style="background-color:{COLOR_CODE_BG}; border-radius:8px; padding:18px;">
      <span style="font-family:'Courier New',monospace; font-size:32px; font-weight:700; letter-spacing:8px; color:{COLOR_PRIMARY};">{code}</span>
    </td>
  </tr>
</table>
"""


def verification_code_email(code: str, ttl_minutes: int) -> tuple[str, str, str]:
    subject = f"Votre code de vérification — {BRAND_NAME}"
    text = (
        f"Votre code de vérification est : {code}\n\n"
        f"Il expire dans {ttl_minutes} minutes. Si tu n'es pas à l'origine de cette demande, ignore ce message."
    )
    body_html = f"""\
<h1 style="margin:0 0 12px; font-size:20px; color:{COLOR_TEXT};">Vérifiez votre adresse email</h1>
<p style="margin:0; font-size:15px; line-height:22px; color:{COLOR_MUTED};">
  Utilisez le code ci-dessous pour confirmer votre adresse email.
</p>
{_code_block(code)}
<p style="margin:0; font-size:14px; line-height:20px; color:{COLOR_MUTED};">
  Ce code expire dans {ttl_minutes} minutes. Si tu n'es pas à l'origine de cette demande, ignore simplement ce message.
</p>
"""
    return subject, text, _layout(preheader=f"Votre code : {code}", title=subject, body_html=body_html)


def password_reset_email(code: str, ttl_minutes: int) -> tuple[str, str, str]:
    subject = f"Réinitialisation de mot de passe — {BRAND_NAME}"
    text = (
        f"Votre code de réinitialisation est : {code}\n\n"
        f"Il expire dans {ttl_minutes} minutes. Si tu n'es pas à l'origine de cette demande, ignore ce message."
    )
    body_html = f"""\
<h1 style="margin:0 0 12px; font-size:20px; color:{COLOR_TEXT};">Réinitialisation de mot de passe</h1>
<p style="margin:0; font-size:15px; line-height:22px; color:{COLOR_MUTED};">
  Utilisez le code ci-dessous pour choisir un nouveau mot de passe.
</p>
{_code_block(code)}
<p style="margin:0; font-size:14px; line-height:20px; color:{COLOR_MUTED};">
  Ce code expire dans {ttl_minutes} minutes. Si tu n'es pas à l'origine de cette demande, ton mot de passe reste inchangé — ignore simplement ce message.
</p>
"""
    return subject, text, _layout(preheader=f"Votre code : {code}", title=subject, body_html=body_html)


def order_status_email(shop_name: str, status_label: str) -> tuple[str, str, str]:
    subject = f"Votre commande chez {shop_name} est {status_label}"
    text = (
        f"Bonjour,\n\nVotre commande chez « {shop_name} » est maintenant {status_label}.\n\n"
        "Vous pouvez suivre son statut dans votre espace « Mes commandes »."
    )
    body_html = f"""\
<h1 style="margin:0 0 12px; font-size:20px; color:{COLOR_TEXT};">Votre commande a du nouveau</h1>
<p style="margin:0; font-size:15px; line-height:22px; color:{COLOR_MUTED};">
  Bonjour,<br /><br />
  Votre commande chez <strong style="color:{COLOR_TEXT};">{shop_name}</strong> est maintenant
  <strong style="color:{COLOR_PRIMARY};">{status_label}</strong>.
</p>
<p style="margin:20px 0 0; font-size:14px; line-height:20px; color:{COLOR_MUTED};">
  Vous pouvez suivre son statut dans votre espace « Mes commandes ».
</p>
"""
    return subject, text, _layout(preheader=text.splitlines()[2], title=subject, body_html=body_html)
