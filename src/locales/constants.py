"""
src/locales/constants.py
Static fallback locale definitions.
Used when data/locales.json is missing or updater fails.
This file must stay extremely stable — the entire pipeline depends on it.
"""

# ---------------------------------------------------------------------
# DEFAULT: Core locale → URL path map
#   Key   = locale code used in CSV filenames, logs, dashboard
#   Value = actual path fragment used on kwalee.com
# ---------------------------------------------------------------------

DEFAULT_LOCALES = {
    "en":   "",
    "es":   "es-es",
    "de":   "de-de",
    "fr":   "fr-fr",
    "it":   "it-it",
    "ja":   "ja-jp",
    "ko":   "ko-kr",
    "zhcn": "zh-cn",
    "zhtw": "zh-tw",
    "ptbr": "pt-br",
    "ptpt": "pt-pt",
    "ru":   "ru-ru",
    "ar":   "ar-sa",
    "pl":   "pl-pl",
    "sv":   "sv-se",
    "uk":   "uk-ua",
    "tr":   "tr-tr",
    "nb":   "nb-no",
    "da":   "da-dk",
}

# ---------------------------------------------------------------------
# RELEASE CONTROL
# For production: Only these locales should run automatically
# ---------------------------------------------------------------------
RELEASED = [
    "en", "es", "de", "fr", "it",
    "ko", "ja", "zhcn", "zhtw",
    "ptbr", "ptpt", "ru", "tr", "uk",
    "pl", "sv", "nb", "ar", "da",
]

# ---------------------------------------------------------------------
# Unreleased (planned but not yet fully supported)
# These will not run unless CLI or ENV explicitly includes them.
# ---------------------------------------------------------------------
UNRELEASED = []