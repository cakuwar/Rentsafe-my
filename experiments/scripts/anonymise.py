"""Anonymise conversation text before it is sent to an external API (E4).

Order matters: specific patterns run before general ones.
  names      the project's own list (data/samples/redact.txt, read-only; the
             same list nlp-service/training/redaction.py uses) plus the agent
             names and companies recorded for the blind-test cases
             (data/test_real/cases/*/input.json); longest first, no word
             boundaries (OCR glues words), case-insensitive -> [NAME] / [COMPANY]
             plus a private extra list found by reviewing the blind transcripts
             (~/rentsafe_experiments_data/blind/extra_redact.txt, outside the repo);
             single name fragments need whole-word matches -> [NAME] / [ADDRESS]
  honorific  Encik/Puan/Cik/Mr/Ms/Bro/Kak/... followed by a capitalised word -> [NAME]
  address    "12, Jalan X", "Block E-17-1" style street addresses -> [ADDRESS]
  email      -> [EMAIL]
  URL        http(s)://, www., wa.me/, and bare domains (.com, .my, .net, ...) -> [URL]
  REN        "REN 12345", "REN: 12345", "E 1234" style agent numbers -> [REN]
  IC         yymmdd-xx-xxxx -> [IC]
  numbers    nine or more digits joined by single spaces/hyphens (the project's
             phone pattern): Malaysian mobiles (01x / 601x / +601x) -> [PHONE],
             any other such number -> [ACCOUNT]
Prices (RM1,200), dates and short numbers are left alone.
"""
import glob
import json
import os
import re

REPO = r"C:\Users\U S E R\Documents\fyp\rentsafe-my"
REDACT_LIST = os.path.join(REPO, "data", "samples", "redact.txt")
CASES = os.path.join(REPO, "data", "test_real", "cases")
# Names and street addresses found by reviewing the anonymised blind transcripts;
# kept outside the repo like redact.txt.
EXTRA_LIST = os.path.join(os.path.expanduser("~"), "rentsafe_experiments_data", "blind", "extra_redact.txt")
HONORIFIC_WORDS = {"encik", "puan", "cik", "tuan", "dato", "datin", "haji", "ustaz", "madam",
                   "mister", "miss", "akak", "abang", "uncle", "aunty", "auntie"}
ADDRESS = re.compile(
    r"\b[A-Z]?\d+[A-Za-z]?(?:-\d+)*\s*,\s*(?:Jalan|Jln|Lorong|Larong|Lrg|Persiaran)\s+[A-Za-z]+(?:\s+[\w/]+)?"
    r"|\bBlo(?:ck|k)\s+[A-Z]-?\d+(?:-\d+)+", re.IGNORECASE)

HONORIFIC = re.compile(
    r"\b(Encik|En\.|Puan|Pn\.|Cik|Tuan|Dato'?|Datin|Haji|Hj\.?|Ustaz|Mr\.?|Mrs\.?|Ms\.?|Miss|Madam|"
    r"Bro|Sis|Kak|Akak|Abang|Abg|Uncle|Aunty|Auntie)\s+([A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+)?)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(r"(?:https?://|www\.|wa\.me/)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|my|net|org|io|co|gov|edu)(?:\.my)?(?:/\S*)?\b",
                 re.IGNORECASE)
REN = re.compile(r"\bREN\s*[:.#-]?\s*\d{3,6}\b|\bE\s?\d{4,5}\b", re.IGNORECASE)
IC = re.compile(r"\b\d{6}-\d{2}-\d{4}\b")
LONG_NUMBER = re.compile(r"\+?\d(?:[\s-]?\d){8,}")
MOBILE = re.compile(r"^\+?(?:6\s?-?)?0?1\d")


def _common_words():
    """Words found in 3+ corpus conversations: a name fragment that is also a
    common word (e.g. an agent called "Home Rental") is not redacted on its own."""
    import csv
    path = os.path.join(os.path.expanduser("~"), "rentsafe_experiments_data", "run1_data", "train.csv")
    df = {}
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            for w in set(re.findall(r"[a-z]+", row["text"].lower())):
                df[w] = df.get(w, 0) + 1
    return {w for w, n in df.items() if n >= 3}


def _read_list(path, boundary):
    entries = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tag = "[NAME]"
            m = re.match(r"(\[[\w-]+\])\s+(.+)", line)
            if m:
                tag, line = m.group(1).upper(), m.group(2)
            entries.append((line, tag, boundary))
    return entries


def _list_entries():
    """(regex, tag). Full names from the lists and forms match without word
    boundaries, as in redaction.py (OCR glues words). Single name fragments and
    the extra list need whole-word matches, so "Puan" or a short first name is
    never removed from inside an ordinary word such as "perempuan"."""
    common = _common_words()
    entries = _read_list(REDACT_LIST, False) + _read_list(EXTRA_LIST, True)
    for path in glob.glob(os.path.join(CASES, "case*", "input.json")):
        agent = json.load(open(path, encoding="utf-8-sig")).get("agent") or {}
        for key, tag in (("company", "[COMPANY]"), ("name", "[NAME]")):
            value = (agent.get(key) or "").strip()
            if len(value) >= 3:
                entries.append((value, tag, len(value.split()) == 1))
                if tag == "[NAME]" and len(value.split()) > 1:
                    entries += [(part, tag, True) for part in value.split()
                                if len(part) >= 4 and part.lower() not in common
                                and part.lower().strip(".'") not in HONORIFIC_WORDS]
    seen, unique = set(), []
    for text, tag, boundary in sorted(entries, key=lambda e: len(e[0]), reverse=True):
        if text.lower() not in seen:
            seen.add(text.lower())
            body = r"\s*".join(map(re.escape, text.split()))
            unique.append((rf"(?<![A-Za-z]){body}(?![A-Za-z])" if boundary else body, tag))
    return unique


_ENTRIES = _list_entries()


def _number(match):
    digits = re.sub(r"[\s-]", "", match.group(0))
    return "[PHONE]" if MOBILE.match(digits) else "[ACCOUNT]"


def anonymise(text):
    """Returns (anonymised text, {placeholder: count})."""
    counts = {}

    def sub(pattern, repl, s, flags=0):
        def wrap(m):
            out = repl(m) if callable(repl) else repl
            counts[out] = counts.get(out, 0) + 1
            return out
        return re.sub(pattern, wrap, s, flags=flags)

    def honorific(m):
        counts["[NAME]"] = counts.get("[NAME]", 0) + 1
        return f"{m.group(1)} [NAME]"

    for pattern, tag in _ENTRIES:
        text = sub(pattern, tag, text, flags=re.IGNORECASE)
    text = HONORIFIC.sub(honorific, text)
    text = sub(ADDRESS, "[ADDRESS]", text)
    text = sub(EMAIL, "[EMAIL]", text)
    text = sub(URL, "[URL]", text)
    text = sub(REN, "[REN]", text)
    text = sub(IC, "[IC]", text)
    text = sub(LONG_NUMBER, _number, text)
    return text, counts


def leaks(text):
    """Anything that still looks like personal data after anonymise()."""
    found = [pat for pat, _ in _ENTRIES if re.search(pat, text, re.IGNORECASE)]
    for name, pattern in (("email", EMAIL), ("ic", IC), ("long number", LONG_NUMBER), ("address", ADDRESS)):
        if pattern.search(text):
            found.append(name)
    return found
