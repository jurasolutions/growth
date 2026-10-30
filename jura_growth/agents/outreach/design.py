"""The designed HTML part of an outreach email (scout PRD §5.6a).

One white column, at most 600 px, on table markup with every style inline, so
it reads the same in Gmail, Outlook and Apple Mail. A short `<style>` block
only adds what inline styles can't: stacking the signature on a phone, and
dark-mode colours for the clients that honour them (Apple Mail, and Outlook
through `[data-ogsc]`). Gmail's own dark mode inverts the colours itself; the
mark sits on a white tile inside its PNG, so it stays legible there too.

No hero banner and no image-only content: the one image is the 48 px mark, the
wordmark beside it is text, and the image has alt text, so the email reads in
full with images blocked. No tracking pixel.

Every colour and font stack below is copied from `design-system/tokens/`
(read-only), named after its token.
"""

from __future__ import annotations

import html

from jura_growth.agents.scout import settings

# design-system/tokens/colors.css
WHITE = "#ffffff"  # --white, --surface-page
NEUTRAL_25 = "#fafbfa"  # --neutral-25
NEUTRAL_200 = "#dfe3e0"  # --neutral-200, --border-subtle (hairlines)
NEUTRAL_300 = "#c6ccc8"  # --neutral-300
NEUTRAL_400 = "#9aa39d"  # --neutral-400
NEUTRAL_500 = "#6f7973"  # --neutral-500, --text-muted (the footer)
NEUTRAL_600 = "#4e5852"  # --neutral-600 ("Solutions" in the lockup)
NEUTRAL_700 = "#363e39"  # --neutral-700, --text-body
NEUTRAL_800 = "#222824"  # --neutral-800
NEUTRAL_900 = "#141814"  # --neutral-900, --text-strong
GREEN_300 = "#86b89e"  # --green-300 (links in dark mode)
GREEN_500 = "#2a7854"  # --green-500 (the button in dark mode)
GREEN_600 = "#0f5132"  # --green-600, --brand: links, the button, the rule, the mark

# design-system/tokens/typography.css
FONT_DISPLAY = "'Outfit','Helvetica Neue',Helvetica,Arial,sans-serif"
FONT_BODY = "'DM Sans','Helvetica Neue',Helvetica,Arial,sans-serif"
FONT_MONO = "'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

# The template's name on the approval card. Bump it with any change to the frame;
# the approval hash covers the rendered frame itself either way
# (`compose.frame_fingerprint`), so a change supersedes pending approvals.
TEMPLATE_VERSION = "designed email v1 (Levi's signature, 2026-10-31)"

CALL_LABEL = "Book a 30-minute call"
TAGLINE = "We automate the repetitive parts of running a business."
SESSION_LABEL = "Book a discovery session →"
WORDMARK_TAGLINE = "AUTOMATION CONSULTANCY"

# Phone width and dark mode. Classes only switch what the inline styles set.
STYLE = f"""
:root {{ color-scheme: light dark; supported-color-schemes: light dark; }}
@media only screen and (max-width: 600px) {{
  .jm-pad {{ padding: 28px 20px !important; }}
  .jm-stack {{ display: block !important; width: 100% !important; }}
  .jm-rule {{ display: none !important; }}
  .jm-contact {{ padding: 14px 0 0 !important; }}
  .jm-tap {{ display: block !important; min-height: 44px !important; line-height: 44px !important; }}
}}
@media (prefers-color-scheme: dark) {{
  .jm-bg {{ background: {NEUTRAL_900} !important; }}
  .jm-text {{ color: {NEUTRAL_200} !important; }}
  .jm-strong {{ color: {WHITE} !important; }}
  .jm-muted {{ color: {NEUTRAL_400} !important; }}
  .jm-link {{ color: {GREEN_300} !important; }}
  .jm-btn {{ background: {GREEN_500} !important; border-color: {GREEN_500} !important; }}
  .jm-line {{ border-color: {NEUTRAL_700} !important; }}
}}
[data-ogsc] .jm-text {{ color: {NEUTRAL_200} !important; }}
[data-ogsc] .jm-strong {{ color: {WHITE} !important; }}
[data-ogsc] .jm-muted {{ color: {NEUTRAL_400} !important; }}
[data-ogsc] .jm-link {{ color: {GREEN_300} !important; }}
[data-ogsb] .jm-bg {{ background: {NEUTRAL_900} !important; }}
"""


def _a(href: str, text: str, style: str, cls: str = "jm-link") -> str:
    """A link; `cls` holds the classes the style block switches."""
    return f'<a href="{html.escape(href, quote=True)}" class="{cls}" style="{style}">{text}</a>'


LINK = f"color:{GREEN_600};text-decoration:underline;"
WRAP = "overflow-wrap:anywhere;word-break:break-word;"


def button(href: str) -> str:
    """A bulletproof button: the green cell carries the colour everywhere, and
    the link's border makes the whole button tappable (Outlook ignores padding
    on links, not borders)."""
    link = (
        f"display:inline-block;border:14px solid {GREEN_600};border-left-width:24px;border-right-width:24px;"
        f"border-radius:6px;background:{GREEN_600};color:#ffffff;font-family:{FONT_BODY};font-size:16px;"
        "font-weight:700;line-height:20px;text-decoration:none;"
    )
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 32px;">'
        f'<tr><td class="jm-btn" bgcolor="{GREEN_600}" style="background:{GREEN_600};border-radius:6px;">'
        + _a(href, CALL_LABEL, link, "jm-btn")
        + "</td></tr></table>"
    )


def signature(*, home_href: str, session_href: str, mark_url: str) -> str:
    """Levi's signature, as Ting Yu gave it: the mark and the name block on the
    left, a deep-green rule, the email address and the site on the right, then
    a hairline and the tagline."""
    mark = (
        f'<img src="{html.escape(mark_url, quote=True)}" width="48" height="48" alt="Jura Solutions" '
        f'style="display:block;width:48px;height:48px;border:0;outline:none;text-decoration:none;'
        f'font-family:{FONT_BODY};font-size:11px;line-height:14px;color:{GREEN_600};">'
    )
    name_block = (
        f'<p class="jm-strong" translate="no" style="margin:0;font-family:{FONT_DISPLAY};font-size:17px;line-height:22px;'
        f'font-weight:600;letter-spacing:-0.01em;color:{NEUTRAL_900};">{html.escape(settings.SIGNATURE_NAME)}</p>'
        f'<p class="jm-muted" style="margin:0 0 8px;font-family:{FONT_BODY};font-size:14px;line-height:20px;'
        f'color:{NEUTRAL_600};">{html.escape(settings.SIGNATURE_TITLE)}</p>'
        f'<p class="jm-text" translate="no" style="margin:0;font-family:{FONT_DISPLAY};font-size:15px;line-height:20px;'
        f'letter-spacing:-0.01em;color:{NEUTRAL_600};">'
        f'<strong class="jm-strong" style="font-weight:600;color:{NEUTRAL_900};">Jura</strong> Solutions</p>'
        f'<p class="jm-link" style="margin:2px 0 0;font-family:{FONT_MONO};font-size:12px;line-height:16px;'
        f'letter-spacing:0.08em;color:{GREEN_600};">{WORDMARK_TAGLINE}</p>'
    )
    contact_link = f"color:{GREEN_600};text-decoration:none;font-family:{FONT_BODY};font-size:14px;line-height:22px;"
    contact = (
        f'<p translate="no" style="margin:0;font-family:{FONT_BODY};font-size:14px;line-height:22px;">'
        + _a(f"mailto:{settings.SIGNATURE_EMAIL}", html.escape(settings.SIGNATURE_EMAIL), contact_link, "jm-link jm-tap")
        + f'</p><p translate="no" style="margin:0;font-family:{FONT_BODY};font-size:14px;line-height:22px;">'
        + _a(home_href, settings.SITE, contact_link, "jm-link jm-tap")
        + "</p>"
    )
    return (
        '<table role="presentation" id="signature" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="border-collapse:collapse;">'
        "<tr>"
        '<td class="jm-stack" valign="top" style="padding:0 20px 0 0;vertical-align:top;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;"><tr>'
        f'<td valign="top" style="padding:2px 14px 0 0;vertical-align:top;width:48px;">{mark}</td>'
        f'<td valign="top" style="vertical-align:top;">{name_block}</td>'
        "</tr></table></td>"
        f'<td class="jm-rule" id="signature-rule" width="2" style="width:2px;background:{GREEN_600};'
        'font-size:0;line-height:0;">&nbsp;</td>'
        '<td class="jm-stack jm-contact" valign="middle" style="padding:0 0 0 20px;vertical-align:middle;">'
        f"{contact}</td>"
        "</tr>"
        '<tr><td colspan="3" style="height:16px;font-size:0;line-height:0;">&nbsp;</td></tr>'
        '<tr><td colspan="3" id="signature-hairline" class="jm-line" '
        f'style="padding:16px 0 0;border-top:1px solid {NEUTRAL_200};font-size:0;line-height:0;">&nbsp;</td></tr>'
        f'<tr><td colspan="3" style="padding:0;">'
        f'<p class="jm-text" style="margin:0;font-family:{FONT_BODY};font-size:14px;line-height:22px;color:{NEUTRAL_700};">'
        f"{html.escape(TAGLINE)} "
        + _a(session_href, html.escape(SESSION_LABEL), f"color:{GREEN_600};text-decoration:none;font-weight:700;white-space:nowrap;",
             "jm-link jm-tap")
        + "</p></td></tr></table>"
    )


def page(*, subject: str, body_html: str, call_href: str, home_href: str, mark_url: str, footer_html: str) -> str:
    """The whole HTML email. `body_html` is the model's paragraphs, already
    escaped and linked; `footer_html` the legal footer's inner HTML."""
    text_style = f"font-family:{FONT_BODY};font-size:16px;line-height:26px;color:{NEUTRAL_700};"
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="x-apple-disable-message-reformatting">'
        '<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">'
        f"<title>{html.escape(subject)}</title>\n<style>{STYLE}</style></head>\n"
        f'<body class="jm-bg" style="margin:0;padding:0;background:{WHITE};">\n'
        f'<table role="presentation" class="jm-bg" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{WHITE};border-collapse:collapse;"><tr><td align="center" style="padding:0;">\n'
        '<!--[if mso]><table role="presentation" width="600" align="center" cellpadding="0" cellspacing="0" '
        'border="0"><tr><td><![endif]-->\n'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="width:100%;max-width:600px;border-collapse:collapse;">\n'
        f'<tr><td class="jm-pad jm-text" style="padding:40px 32px 32px;text-align:left;{text_style}">\n'
        f"{body_html}\n{button(call_href)}\n"
        f"{signature(home_href=home_href, session_href=call_href, mark_url=mark_url)}\n"
        "</td></tr>\n"
        '<tr><td class="jm-pad" style="padding:0 32px 40px;">'
        f'<p id="footer" class="jm-muted jm-line" style="margin:0;padding:20px 0 0;border-top:1px solid {NEUTRAL_200};'
        f'font-family:{FONT_BODY};font-size:13px;line-height:20px;color:{NEUTRAL_500};{WRAP}">{footer_html}</p>'
        "</td></tr>\n</table>\n<!--[if mso]></td></tr></table><![endif]-->\n</td></tr></table>\n</body></html>\n"
    )


def paragraph(inner: str) -> str:
    return (
        f'<p class="jm-text" style="margin:0 0 18px;font-family:{FONT_BODY};font-size:16px;line-height:26px;'
        f'color:{NEUTRAL_700};{WRAP}">{inner}</p>'
    )
