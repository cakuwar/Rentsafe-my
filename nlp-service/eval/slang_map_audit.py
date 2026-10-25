"""Find slang entries that collide with ordinary English words.

The shortform dictionary is sourced from Malay SMS glossaries, where "come" is a
shorthand for "comel" (cute). RentSafe's conversations are code-switched, so the
same entry rewrites the English verb: "come by on Saturday" became "comel by on
saturday" in a real request. Every such entry corrupts text before it reaches
layer 1's patterns.

An entry is reported when its short_form is a common English word AND the
normalised form is something else — i.e. the rewrite changes meaning for anyone
writing English.

    python eval/slang_map_audit.py

Writes eval/results/slang_map_audit.json.
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(
    HERE, "..", "app", "normaliser",
    "rentsafe_manglish_shortform_dictionary_v2.csv",
)
OUT = os.path.join(HERE, "results", "slang_map_audit.json")

# Common English words, weighted toward what appears in rental conversations.
ENGLISH = {
    # rental domain
    "rent", "rental", "room", "unit", "house", "home", "deposit", "agreement",
    "tenant", "owner", "landlord", "agent", "key", "keys", "view", "viewing",
    "move", "lease", "book", "booking", "pay", "paid", "payment", "transfer",
    "bank", "account", "month", "monthly", "week", "day", "price", "cost",
    "available", "furnished", "parking", "water", "electric", "utility",
    # high-frequency general
    "come", "came", "can", "will", "want", "need", "know", "take", "give",
    "make", "made", "send", "sent", "show", "tell", "ask", "call", "meet",
    "see", "look", "find", "keep", "let", "put", "get", "got", "go", "went",
    "do", "does", "did", "done", "have", "has", "had", "is", "are", "was",
    "were", "be", "been", "the", "and", "for", "with", "from", "this", "that",
    "there", "here", "when", "where", "what", "who", "how", "why", "all",
    "any", "some", "more", "most", "other", "than", "then", "now", "just",
    "only", "also", "very", "too", "much", "many", "first", "last", "next",
    "new", "old", "good", "bad", "best", "sure", "okay", "yes", "no", "not",
    "please", "thanks", "sorry", "hello", "hi", "bye", "time", "date", "name",
    "number", "place", "area", "side", "back", "front", "top", "end", "part",
    "line", "list", "case", "point", "fact", "form", "hand", "eye", "face",
    "man", "woman", "people", "person", "child", "family", "friend", "work",
    "job", "money", "cash", "card", "phone", "mail", "text", "chat", "photo",
    "picture", "video", "file", "link", "site", "page", "post", "share",
    "check", "confirm", "cancel", "start", "stop", "wait", "help", "try",
    "use", "open", "close", "lock", "safe", "real", "fake", "same", "different",
    "one", "two", "three", "four", "five", "ten", "half", "full", "free",
}


def main():
    with open(CSV_PATH, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    collisions = []
    for row in rows:
        short = (row.get("short_form") or "").strip().lower()
        normalised = (row.get("normalised_form") or "").strip().lower()
        if not short or not normalised or short == normalised:
            continue
        if short in ENGLISH:
            collisions.append({
                "short_form": short,
                "normalised_form": normalised,
                "category": row.get("category", ""),
                "source": row.get("source_detail", "")[:60],
                "also_english": normalised in ENGLISH,
            })

    print(f"{len(rows)} entries, {len(collisions)} collide with English words")
    print()
    print(f"{'short_form':<14} {'-> normalised':<22} category")
    print("-" * 62)
    for item in sorted(collisions, key=lambda c: c["short_form"]):
        print(f"{item['short_form']:<14} -> {item['normalised_form']:<19} "
              f"{item['category']}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as handle:
        json.dump(
            {"entries": len(rows), "collisions": collisions}, handle, indent=2
        )
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
