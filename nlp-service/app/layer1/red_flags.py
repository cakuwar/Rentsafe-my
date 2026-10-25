"""Layer 1 — bilingual (BM + EN) rule-based scam signal extraction.

Deterministic and explainable. Layer 2 is a black box, so this module is the
only part of the verdict that can be shown to a renter as a reason, which is why
every rule carries a human-readable label and advice in both languages.

Three things distinguish this from a bag of keywords:

**Exceptions.** A match is suppressed when the surrounding sentence negates it
("jangan bayar sebelum tengok" is advice, not a demand), asks it as a question
("urgent ke?"), or scopes it to a time ("tak boleh tengok hujung minggu" is a
busy landlord, not a refusal to show the unit). Suppressed matches are returned
in `suppressed` rather than dropped, so a debugging session can see them.

**Pattern rules.** Individual flags are weak; the combinations are the scam. A
refund promise next to a payment demand is the refundable-hold lure, and naming
it lets the narrator describe the tactic rather than list words.

**Legitimacy signals** are reported as context, never as cancellation. A REN
number or a tenancy agreement can be fabricated, so the narrator's job is to say
"a REN number was quoted — verify it at lppeh.gov.my", not to lower a score.

Severity is display priority only. It orders evidence in the UI and tells the
narrator what to lead with. It is never summed, and this module produces no score
of any kind: scoring belongs to layer 2 and the backend.

Patterns were written from the labelled corpus and from real WhatsApp scam
screenshots. They deliberately encode scam *mechanics* rather than the phrases
that happen to be frequent — the synthetic corpus comes from ~20 templates, so
its most "discriminative" n-grams are template fingerprints, and matching those
would recognise the generator rather than a scam. That failure is documented for
the layer-2 model in docs/MODEL_COMPARISON.md.
"""
import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Exception cues
# --------------------------------------------------------------------------

# Looking backwards from a match: "don't pay before viewing" is safety advice.
_NEGATION = re.compile(
    r"\b(?:jangan|jgn|tak\s+payah|tk\s+payah|tidak\s+perlu|xpayah|elak|"
    r"don'?t|do\s+not|never|no\s+need\s+to|avoid|without)\b",
    re.IGNORECASE,
)

# A day or time qualifier turns a refusal into a scheduling constraint.
_TIMING = re.compile(
    # A specific day or date, not a vague "now": "cannot view now" reads as a
    # refusal, while "tak boleh tengok hujung minggu" is a busy landlord.
    r"\b(?:hari\s+ini|harini|esok|lusa|minggu\s+(?:ini|depan)|hujung\s+minggu|"
    r"weekend|today|tomorrow|this\s+week|next\s+week|"
    r"isnin|selasa|rabu|khamis|jumaat|sabtu|ahad|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?\n])\s+")

# --------------------------------------------------------------------------
# Entities — extracted for the narrator and redacted out of snippets
# --------------------------------------------------------------------------

_ENTITY_PATTERNS = {
    "phone": re.compile(r"\b(?:\+?60|0)1\d[-\s]?\d{3,4}[-\s]?\d{4}\b"),
    "ic": re.compile(r"\b\d{6}[-\s]?\d{2}[-\s]?\d{4}\b"),
    "account": re.compile(r"\b\d{10,16}\b"),
    "amount": re.compile(r"\brm\s?\d[\d,]*(?:\.\d{2})?\b", re.IGNORECASE),
    "url": re.compile(r"\bhttps?://\S+|\bwa\.me/\S+", re.IGNORECASE),
}

# Amounts stay visible: they are evidence, not personal data.
_REDACT = ("phone", "ic", "account", "url")


@dataclass(frozen=True)
class Rule:
    """One detector. `exceptions` names which suppression checks apply."""

    id: str
    category: str
    severity: str
    patterns: tuple[str, ...]
    label_en: str
    label_ms: str
    advice_en: str
    advice_ms: str
    exceptions: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    compiled: tuple = field(default=(), compare=False, repr=False)


def _rule(**kwargs) -> Rule:
    rule = Rule(**kwargs)
    object.__setattr__(
        rule,
        "compiled",
        tuple(re.compile(p, re.IGNORECASE) for p in rule.patterns),
    )
    return rule


# --------------------------------------------------------------------------
# Rule catalogue
# --------------------------------------------------------------------------

RULES: tuple[Rule, ...] = (
    # ---------------- critical ----------------
    _rule(
        id="pay_before_viewing",
        category="payment",
        severity="critical",
        sources=("S1", "S2", "S4"),
        exceptions=("negation",),
        label_en="Payment demanded before you can view",
        label_ms="Bayaran diminta sebelum anda boleh melihat unit",
        advice_en="Never pay before seeing the unit in person. This is the single "
                  "most common rental scam in Malaysia.",
        advice_ms="Jangan sekali-kali bayar sebelum melihat unit sendiri. Ini "
                  "penipuan sewa paling biasa di Malaysia.",
        patterns=(
            r"\b(?:bayar|transfer|deposit|booking|tempah|lock)\b[^.!?\n]{0,60}?"
            r"\b(?:baru|sebelum|then|before)\b[^.!?\n]{0,35}?"
            r"\b(?:view|viewing|tengok|lihat|masuk|kunci|key|date|time)\b",
            r"\blepas\s+(?:view|transfer|bayar)\b",
            r"\bafter\s+(?:you\s+)?(?:transfer|pay|book)\b",
            r"\b(?:kalau|klu|klau|if)\b[^.!?\n]{0,45}?\b(?:x\s*jadi|xjadi|tak\s*jadi|"
            r"tk\s*jadi|takjadi|tak\s+sesuai|tak\s+suka|tak\s+berkenan|tak\s+ok|"
            r"not\s+proceed|not\s+suitable|don'?t\s+like|change\s+your\s+mind)\b"
            r"[^.!?\n]{0,50}(?:\b(?:dpt|dapat)\s+balik\b|\brefund|\bmoney\s+back\b)",
        ),
    ),
    _rule(
        id="viewing_fee",
        category="payment",
        severity="critical",
        sources=("S2", "S3"),
        exceptions=("negation",),
        label_en="A fee is charged just to view",
        label_ms="Yuran dikenakan semata-mata untuk melihat unit",
        advice_en="Viewing a rental is always free. Any fee to view is a scam.",
        advice_ms="Melihat rumah sewa sentiasa percuma. Sebarang yuran untuk "
                  "melihat adalah penipuan.",
        patterns=(
            r"\b(?:yuran|fee|caj|charge)\s+(?:untuk\s+)?(?:viewing|view|tengok|lawat)\b",
            r"\b(?:viewing|view)\s+(?:fee|charge|caj)\b",
            r"\b(?:bayar|pay)\s+rm\s?\d[\d,]*\s*(?:untuk|to|for)\s+(?:view|viewing|tengok)\b",
        ),
    ),
    _rule(
        id="otp_tac_request",
        category="identity",
        severity="critical",
        sources=("S1",),
        exceptions=("negation",),
        label_en="One-time password or TAC requested",
        label_ms="Kata laluan sekali guna atau TAC diminta",
        advice_en="No landlord ever needs your OTP or TAC. Sharing it lets someone "
                  "empty your bank account.",
        advice_ms="Tiada tuan rumah yang perlukan OTP atau TAC anda. Berkongsi "
                  "kod itu membolehkan akaun bank anda dikosongkan.",
        patterns=(
            r"\b(?:hantar|bagi|share|send|bg)\b[^.!?\n]{0,30}\b(?:kod\s+)?(?:otp|tac)\b",
            r"\b(?:otp|tac)\b[^.!?\n]{0,25}\b(?:yang\s+)?masuk\b",
            r"\b(?:no|nombor)\s+(?:otp|tac)\b",
        ),
    ),
    # ---------------- high ----------------
    _rule(
        id="third_party_account",
        category="channel",
        severity="high",
        sources=("S2", "S7"),
        label_en="Money goes to someone else's account",
        label_ms="Wang dihantar ke akaun orang lain",
        advice_en="Payment should go to the verified owner. A different account "
                  "name makes the money untraceable to them.",
        advice_ms="Bayaran patut kepada pemilik yang disahkan. Nama akaun berbeza "
                  "menyukarkan wang dikesan kepada mereka.",
        patterns=(
            r"\b(?:company|owner\s+company|syarikat)\s+account\b",
            r"\bakaun\s+(?:syarikat|company)\b",
            r"\bbank\s+in\s+(?:ke\s+)?akaun\s+(?:adik|abang|kawan|isteri|suami|anak)\b",
            r"\bnama\s+akaun\s+(?:lain|berbeza)\b",
            r"\btransfer\s+to\s+(?:my\s+)?(?:agent|company|boss|friend)\b",
            r"\bakaun\s+(?:atas\s+)?nama\s+(?:orang\s+)?lain\b",
        ),
    ),
    _rule(
        id="crypto_or_remittance",
        category="channel",
        severity="high",
        sources=("S3",),
        label_en="Cryptocurrency or overseas transfer requested",
        label_ms="Mata wang kripto atau pindahan luar negara diminta",
        advice_en="Rent is never paid in crypto or by remittance. These channels "
                  "cannot be reversed or traced.",
        advice_ms="Sewa tidak pernah dibayar dengan kripto atau kiriman wang. "
                  "Saluran ini tidak boleh dipulangkan atau dikesan.",
        patterns=(
            r"\b(?:usdt|bitcoin|btc|ethereum|eth|crypto|binance)\b",
            r"\b(?:western\s+union|moneygram|remittance|wise\s+transfer)\b",
            r"\bakaun\s+luar\s+negara\b",
            r"\boverseas\s+(?:bank\s+)?account\b",
        ),
    ),
    _rule(
        id="key_courier",
        category="verification",
        severity="high",
        sources=("S2",),
        label_en="Keys will be posted or couriered",
        label_ms="Kunci akan diposkan atau dihantar melalui kurier",
        advice_en="Keys are handed over in person at the unit. Posting them is a "
                  "way to avoid ever meeting you.",
        advice_ms="Kunci diserahkan sendiri di unit. Menghantar melalui pos ialah "
                  "cara mengelak daripada bertemu anda.",
        patterns=(
            r"\b(?:pos|post|courier|hantar)\s+(?:kan\s+)?(?:the\s+|you\s+the\s+)?"
            r"(?:kunci|key|keys)\b",
            r"\b(?:kunci|key|keys)\s+(?:akan\s+)?(?:di)?(?:pos|post|courier|hantar)\b",
            r"\baccess\s+card\s+(?:akan\s+)?(?:di)?(?:pos|post|courier|hantar)\b",
            r"\bmail\s+(?:you\s+)?the\s+key\b",
        ),
    ),
    _rule(
        id="viewing_denial",
        category="verification",
        severity="high",
        sources=("S4", "S2"),
        exceptions=("timing", "question"),
        label_en="Viewing the unit is refused",
        label_ms="Permintaan melihat unit ditolak",
        advice_en="Walk away if you cannot see the unit. There may be no unit, or "
                  "it may belong to someone else.",
        advice_ms="Berundur jika anda tidak boleh melihat unit. Mungkin tiada unit, "
                  "atau ia milik orang lain.",
        patterns=(
            r"\b(?:tak|tk|x|tidak)\s*(?:boleh|dpt|dapat)\s+(?:view|viewing|tengok|"
            r"masuk|lawat)\b",
            r"\bunit\s+(?:ni\s+)?tak\s+boleh\s+di(?:lawat|tengok)\b",
            r"\bcannot\s+(?:view|open|show)\b",
            r"\bno\s+viewing\b",
            r"\bview(?:ing)?\s+(?:is\s+)?not\s+(?:allowed|possible|available)\b",
        ),
    ),
    _rule(
        id="verification_refusal",
        category="verification",
        severity="high",
        sources=("S2", "S6"),
        label_en="Refuses to prove ownership",
        label_ms="Enggan membuktikan pemilikan",
        advice_en="Ask for the title (geran) or assessment bill. A real owner can "
                  "show one; 'just trust me' is not proof.",
        advice_ms="Minta geran atau bil cukai taksiran. Pemilik sebenar boleh "
                  "menunjukkannya; 'percaya saya' bukan bukti.",
        patterns=(
            r"\b(?:tak|tidak|tk)\s+perlu\s+(?:tunjuk|tengok)\s+(?:geran|surat|dokumen)\b",
            r"\bpercaya\s+(?:saja\s+)?(?:saya|sy)\b",
            r"\bsaya\s+bukan\s+(?:scammer|penipu)\b",
            r"\bi'?m\s+not\s+a\s+scam(?:mer)?\b",
            r"\btrust\s+me\s+(?:lah|la|ok|please)\b",
            r"\bno\s+need\s+(?:to\s+)?(?:see|show)\s+(?:the\s+)?(?:title|grant|deed)\b",
        ),
    ),
    # ---------------- medium ----------------
    _rule(
        id="upfront_payment",
        category="payment",
        severity="medium",
        sources=("S5", "S7"),
        exceptions=("negation",),
        label_en="Money requested up front",
        label_ms="Wang diminta terlebih dahulu",
        advice_en="A booking or holding fee before viewing is the usual opening "
                  "move. Confirm the unit and the owner first.",
        advice_ms="Yuran tempahan sebelum melihat unit ialah langkah pembukaan "
                  "biasa. Sahkan unit dan pemilik dahulu.",
        patterns=(
            r"\bkena\s+bayar\b[^.!?\n]{0,40}\b(?:dulu|dlu|awal|advance|first)\b",
            r"\bbayar\b[^.!?\n]{0,30}\b(?:dulu|dlu|awal)\b",
            r"\bdeposit\s+(?:dulu|dlu|awal)\b",
            r"\b(?:booking|reservation)\s+fee\b",
            r"\bbayar\s+booking\b",
            r"\bbooking\s+rm\s*\d",
            r"\b(?:reserve|book|lock|tempah)\s+(?:it\s+|the\s+\w+\s+)?(?:dulu|dlu|first)\b",
            r"\bneed\s+to\s+reserve\b",
            r"\btempah\s+lock\b",
            r"\block\s+(?:the\s+)?(?:unit|bilik|rumah|room)\b",
            r"\bbagi\s+(?:no|nombor)\s+akaun\b",
            r"\bduitnow\s+qr\b",
            r"\btransfer\s+(?:the\s+)?deposit\s+to\s+my\s+account\b",
            r"\b(?:pay|transfer)\b[^.!?\n]{0,40}\b(?:first|before\s+(?:view|viewing))\b",
        ),
    ),
    _rule(
        id="personal_account",
        category="channel",
        severity="medium",
        sources=("S8", "S2"),
        label_en="Payment to a personal account",
        label_ms="Bayaran ke akaun peribadi",
        advice_en="Agencies use company accounts. A personal account offers you no "
                  "recourse if the unit does not exist.",
        advice_ms="Agensi menggunakan akaun syarikat. Akaun peribadi tidak memberi "
                  "anda jalan tuntutan jika unit tidak wujud.",
        patterns=(
            r"\bakaun\s+peribadi\b",
            r"\bpersonal\s+account\b",
            r"\bakaun\s+(?:saya|sy)\b(?!\s+bayar)",
        ),
    ),
    _rule(
        id="non_bank_channel",
        category="channel",
        severity="medium",
        sources=("S3",),
        label_en="Paid through an e-wallet instead of a bank",
        label_ms="Bayaran melalui e-dompet dan bukan bank",
        advice_en="E-wallet transfers are hard to reverse and often unregistered. "
                  "A landlord with no bank account is a warning sign.",
        advice_ms="Pindahan e-dompet sukar dipulangkan dan selalunya tidak "
                  "berdaftar. Tuan rumah tanpa akaun bank ialah tanda bahaya.",
        patterns=(
            r"\b(?:tkda|tiada|takde|tak\s+ada|no)\s+(?:akaun\s+)?bank\b",
            r"\b(?:guna|pakai|use)\s+(?:tng|touch\s*'?n?\s*go|ewallet|e-wallet|"
            r"grabpay|boost|shopeepay)\b",
            r"\btng\s+(?:je|sahaja|only)\b",
        ),
    ),
    _rule(
        id="deadline_pressure",
        category="pressure",
        severity="medium",
        sources=("S2", "S4"),
        exceptions=("negation", "question"),
        label_en="A deadline is put on the payment",
        label_ms="Tempoh masa dikenakan pada bayaran",
        advice_en="A clock on the money exists to stop you checking. A real unit "
                  "will still be there tomorrow.",
        advice_ms="Tekanan masa wujud untuk menghalang anda menyemak. Unit yang "
                  "benar masih ada esok.",
        patterns=(
            r"\b(?:bayar|transfer|tempah|booking|lock)\b[^.!?\n]{0,40}"
            r"\b(?:sebelum|before)\s+\d{1,2}\s*(?:pm|am|malam|pagi)\b",
            r"\b(?:bayar|transfer|booking)\b[^.!?\n]{0,30}\b(?:malam\s+ini|hari\s+ini|"
            r"tonight|today|sekarang\s+juga)\b",
            r"\block\b[^.!?\n]{0,20}\b\d{1,2}\s*(?:pm|am|malam)\b",
            r"\bwithin\s+\d+\s*(?:hours?|jam|minutes?|minit)\b",
        ),
    ),
    _rule(
        id="competition_pressure",
        category="pressure",
        severity="medium",
        sources=("S2",),
        label_en="Claims other people are competing for the unit",
        label_ms="Mendakwa ada orang lain bersaing untuk unit ini",
        advice_en="Manufactured competition is designed to rush you. You cannot "
                  "verify the other people, and usually they do not exist.",
        advice_ms="Persaingan palsu direka untuk menggesa anda. Anda tidak boleh "
                  "mengesahkan orang lain itu, dan biasanya mereka tidak wujud.",
        patterns=(
            r"\bramai\s+(?:orang\s+)?(?:yang\s+|tengah\s+|tgh\s+|dah\s+)*"
            r"(?:tanya|tnya|minat)\b",
            r"\b(?:ada|ramai)\s+(?:yang\s+)?(?:lain\s+)?(?:tanya|tnya|minat)\s+"
            r"(?:juga|jgk)\b",
            r"\bmany\s+(?:people|others)\s+(?:are\s+)?(?:asking|interested|waiting)\b",
            r"\bfirst\s+come\s+first\s+serve\b",
            r"\bnon\s*stop\s+(?:masuk|mesej|whatsapp|wssp)\b",
            r"\b(?:wssp|whatsapp|mesej)\s+non\s*stop\b",
            r"\bmana\s+yang\s+dulu\b",
            r"\bsiapa\s+(?:yang\s+)?(?:cepat|dulu)\b",
        ),
    ),
    _rule(
        id="video_only_viewing",
        category="verification",
        severity="medium",
        sources=("S4",),
        exceptions=("question",),
        label_en="Only a video call viewing is offered",
        label_ms="Hanya tontonan melalui panggilan video ditawarkan",
        advice_en="A video can be of any unit, including one the sender does not "
                  "own. Insist on visiting in person.",
        advice_ms="Video boleh menunjukkan mana-mana unit, termasuk yang bukan "
                  "milik penghantar. Tegaskan lawatan sendiri.",
        patterns=(
            r"\bvideo\s+call\s+(?:je|sahaja|only|saja)\b",
            r"\b(?:je|sahaja|only)\s+(?:boleh\s+)?video\s+call\b",
            r"\bi\s+(?:can\s+)?(?:only\s+)?(?:send|show)\s+(?:you\s+)?(?:a\s+)?video\b",
            r"\btengok\s+(?:melalui\s+)?video\s+(?:je|sahaja)\b",
        ),
    ),
    _rule(
        id="remote_owner",
        category="verification",
        severity="medium",
        sources=("S2", "S3"),
        label_en="Owner says they are away or overseas",
        label_ms="Pemilik mendakwa berada jauh atau di luar negara",
        advice_en="An absent owner is the standard excuse for refusing a viewing "
                  "and for asking a third party to collect.",
        advice_ms="Pemilik yang tiada ialah alasan biasa untuk menolak lawatan "
                  "dan meminta pihak ketiga mengutip bayaran.",
        patterns=(
            r"\boutstation\b",
            r"\b(?:i'?m|saya|sy)\s+(?:kat|di|in|at)\s+(?:luar\s+negara|overseas|abroad)\b",
            r"\boverseas\b",
            r"\bluar\s+negara\b",
            r"\bnot\s+in\s+(?:town|malaysia|kl)\b",
            r"\btiada\s+di\s+(?:sini|malaysia)\b",
            r"\bworking\s+in\s+singapore\b",
            r"\bowner\s+(?:is\s+)?(?:busy|away|not\s+around)\b",
        ),
    ),
    _rule(
        id="meeting_avoidance",
        category="verification",
        severity="medium",
        sources=("S4",),
        exceptions=("timing", "question"),
        label_en="Avoids meeting in person",
        label_ms="Mengelak daripada bertemu secara bersemuka",
        advice_en="Everything in a genuine rental ends with a meeting. Someone who "
                  "never meets you cannot be verified at all.",
        advice_ms="Setiap sewaan yang sah berakhir dengan pertemuan. Orang yang "
                  "tidak pernah bertemu anda tidak boleh disahkan langsung.",
        patterns=(
            r"\b(?:tak|tk|tidak)\s+(?:dapat|boleh)\s+jumpa\b",
            r"\bcannot\s+meet\b",
            r"\btak\s+sempat\s+jumpa\b",
            r"\bno\s+need\s+to\s+meet\b",
        ),
    ),
    _rule(
        id="proxy_collector",
        category="verification",
        severity="medium",
        sources=("S6",),
        label_en="A third party collects the money",
        label_ms="Pihak ketiga mengutip wang",
        advice_en="Deal with the owner or a registered agent you can verify. A "
                  "'representative' adds a layer you cannot check.",
        advice_ms="Berurusan dengan pemilik atau ejen berdaftar yang boleh anda "
                  "sahkan. 'Wakil' menambah lapisan yang tidak boleh disemak.",
        patterns=(
            r"\bsaya\s+wakil\s+(?:tuan\s+rumah|pemilik|owner)\b",
            r"\bowner\s+suruh\s+saya\s+(?:kutip|ambil|collect)\b",
            r"\bi'?m\s+the\s+(?:owner'?s\s+)?representative\b",
            r"\bpihak\s+ketiga\s+(?:akan\s+)?(?:kutip|ambil)\b",
        ),
    ),
    _rule(
        id="selfie_with_ic",
        category="identity",
        severity="medium",
        sources=("S1",),
        exceptions=("negation",),
        label_en="Photo of you holding your IC requested",
        label_ms="Gambar anda memegang kad pengenalan diminta",
        advice_en="A selfie with your IC is enough to open accounts in your name. "
                  "No landlord needs it before a tenancy agreement.",
        advice_ms="Swafoto dengan kad pengenalan cukup untuk membuka akaun atas "
                  "nama anda. Tiada tuan rumah memerlukannya sebelum perjanjian.",
        patterns=(
            r"\bselfie\s+(?:pegang|dengan|with|holding)\s+(?:ic|mykad|kad)\b",
            r"\bgambar\s+(?:anda\s+)?pegang\s+ic\b",
            r"\bphoto\s+(?:of\s+)?(?:you\s+)?holding\s+(?:your\s+)?ic\b",
        ),
    ),
    _rule(
        id="agreement_irregularity",
        category="tenancy",
        severity="medium",
        sources=("S5",),
        label_en="The tenancy terms are irregular",
        label_ms="Terma perjanjian sewa tidak teratur",
        advice_en="A vague or open-ended agreement leaves you with nothing to "
                  "enforce. Insist on a stamped written tenancy.",
        advice_ms="Perjanjian yang kabur tidak memberi anda apa-apa untuk "
                  "dikuatkuasakan. Tegaskan perjanjian bertulis bersetem.",
        patterns=(
            r"\btak\s+perlu\s+renew\b",
            r"\btempoh\s+sewa\s+(?:saya\s+)?tak\s+letak\b",
            r"\bagreement\s+nanti\b",
            r"\bno\s+need\s+(?:for\s+)?(?:a\s+)?(?:tenancy\s+)?agreement\b",
            r"\btak\s+perlu\s+(?:buat\s+)?(?:surat\s+)?perjanjian\b",
        ),
    ),
    # ---------------- low ----------------
    _rule(
        id="refund_promise",
        category="payment",
        severity="low",
        sources=("S1", "S2"),
        label_en="Promises a full refund if you change your mind",
        label_ms="Menjanjikan bayaran balik penuh jika anda berubah fikiran",
        advice_en="The refund promise is what makes paying feel safe. It is a "
                  "promise from someone you have not verified.",
        advice_ms="Janji bayaran balik menjadikan pembayaran terasa selamat. Ia "
                  "janji daripada orang yang belum anda sahkan.",
        patterns=(
            r"\brefund\s+balik\s+sepenuh\s*nya\b",
            r"\bfull\s+refund\b",
            r"\b(?:akan\s+)?refund(?:ed)?\s+(?:100|sepenuhnya|penuh)\b",
            # The conditional form. It also matches pay_before_viewing, and that
            # overlap is deliberate: the refundable_hold_lure pattern rule needs
            # this flag present to recognise the tactic, not just the demand.
            r"\b(?:kalau|klu|klau|if)\b[^.!?\n]{0,45}?\b(?:x\s*jadi|xjadi|tak\s*jadi|"
            r"tk\s*jadi|takjadi|tak\s+sesuai|tak\s+suka|not\s+proceed|"
            r"change\s+your\s+mind)\b[^.!?\n]{0,50}"
            r"(?:\b(?:dpt|dapat)\s+balik\b|\brefund|\bmoney\s+back\b)",
        ),
    ),
    _rule(
        id="rush_language",
        category="pressure",
        severity="low",
        sources=("S2",),
        exceptions=("question",),
        label_en="Rushing language",
        label_ms="Bahasa yang menggesa",
        advice_en="Being hurried is not itself proof of a scam, but it is how one "
                  "stops you checking.",
        advice_ms="Digesa bukan bukti penipuan dengan sendirinya, tetapi itulah "
                  "cara menghalang anda menyemak.",
        patterns=(
            r"\bjangan\s+lam[ab]+t\b",
            r"\burgent\b",
            r"\bcepat\s+sikit\s+(?:ya|ye|ok)\b",
            r"\bhurry\b",
        ),
    ),
    _rule(
        id="social_proof_payment",
        category="pressure",
        severity="low",
        sources=("S2",),
        label_en="Shows that other people already paid",
        label_ms="Menunjukkan orang lain telah pun membayar",
        advice_en="Receipts and testimonials are trivially faked. They prove "
                  "nothing about whether the unit exists.",
        advice_ms="Resit dan testimoni mudah dipalsukan. Ia tidak membuktikan "
                  "apa-apa tentang kewujudan unit.",
        patterns=(
            r"\borang\s+lain\s+dah\s+bayar\b",
            r"\bcontoh\s+resit\b",
            r"\bothers\s+(?:have\s+)?already\s+paid\b",
            r"\bini\s+resit\s+penyewa\s+lain\b",
        ),
    ),
    _rule(
        id="too_good_text",
        category="pricing",
        severity="low",
        sources=("S9", "S4"),
        label_en="Priced suspiciously low",
        label_ms="Harga luar biasa rendah",
        advice_en="Well below market rent is the bait. Compare against similar "
                  "units in the same area.",
        advice_ms="Harga jauh di bawah pasaran ialah umpan. Bandingkan dengan unit "
                  "serupa di kawasan yang sama.",
        patterns=(
            r"\bmurah\s+(?:gila|giler|sangat)\b",
            r"\bbelow\s+market\b",
            r"\bharga\s+bawah\s+pasaran\b",
            r"\bcheapest\s+in\s+(?:the\s+)?area\b",
        ),
    ),
    _rule(
        id="off_platform",
        category="channel",
        severity="low",
        sources=("S2",),
        label_en="Moves the conversation off-platform",
        label_ms="Memindahkan perbualan ke luar platform",
        advice_en="Moving to a private channel removes the record. Keep dealings "
                  "where they can be traced.",
        advice_ms="Berpindah ke saluran peribadi menghilangkan rekod. Kekalkan "
                  "urusan di tempat yang boleh dikesan.",
        patterns=(
            r"\btelegram\s+(?:saya\s+)?(?:je|sahaja|only)\b",
            r"\b(?:contact|hubungi)\s+(?:saya\s+)?(?:di|on|kat)\s+telegram\b",
            r"\bwa\.me/\S+",
            r"\bjangan\s+guna\s+(?:apps?|platform)\s+(?:ni|this)\b",
        ),
    ),
    # -------- beyond the catalogue, kept because they caught real scams -----
    _rule(
        id="personal_details_request",
        category="identity",
        severity="medium",
        sources=("local",),
        exceptions=("negation",),
        label_en="Personal details requested before any meeting",
        label_ms="Butiran peribadi diminta sebelum sebarang pertemuan",
        advice_en="Full name, IC and employment details are for a signed tenancy, "
                  "not for a chat with someone you have not met.",
        advice_ms="Nama penuh, kad pengenalan dan butiran pekerjaan adalah untuk "
                  "perjanjian bertandatangan, bukan untuk sembang dengan orang "
                  "yang belum anda temui.",
        patterns=(
            r"\bnama\s+penuh\b[^.!?\n]{0,60}\b(?:no|nombor|ic|kad\s+pengenalan|"
            r"status\s+pekerjaan|tarikh\s+masuk)\b",
            r"\b(?:ic|mykad)\s+(?:number|no|nombor)\b",
            r"\bfull\s+name\b[^.!?\n]{0,40}\bic\b",
            r"\bcopy\s+of\s+(?:your\s+)?(?:ic|passport)\b",
        ),
    ),
    _rule(
        id="proof_of_payment_request",
        category="payment",
        severity="medium",
        sources=("local",),
        label_en="Proof of transfer demanded",
        label_ms="Bukti pindahan diminta",
        advice_en="The receipt request is the step that confirms the money has "
                  "left your account. By then it is usually gone.",
        advice_ms="Permintaan resit ialah langkah yang mengesahkan wang telah "
                  "keluar dari akaun anda. Selalunya ia sudah hilang.",
        patterns=(
            r"\b(?:share|send|hantar|bagi)\s+(?:me\s+)?(?:the\s+)?(?:receipt|resit|slip)\b",
            r"\b(?:screenshot|ss)\s+(?:of\s+)?(?:the\s+)?(?:transfer|payment|resit|receipt)\b",
            r"\bbukti\s+(?:pembayaran|transfer|bayaran)\b",
        ),
    ),
)

RULES_BY_ID = {rule.id: rule for rule in RULES}

# Backwards compatibility: the old module exposed a {label: [patterns]} dict.
RED_FLAG_PATTERNS: dict[str, list[str]] = {
    rule.id: list(rule.patterns) for rule in RULES
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# --------------------------------------------------------------------------
# Pattern rules — combinations that name the tactic
# --------------------------------------------------------------------------

_PAYMENT_ASK = {"upfront_payment", "pay_before_viewing", "viewing_fee"}

PATTERN_RULES: tuple[dict, ...] = (
    {
        "id": "refundable_hold_lure",
        "label_en": "Refundable holding fee lure",
        "label_ms": "Umpan yuran tempahan boleh dikembalikan",
        "description_en": "A refund promise paired with a payment demand — the "
                          "reassurance exists to make paying feel reversible.",
        "requires": ({"refund_promise"}, _PAYMENT_ASK),
    },
    {
        "id": "pressure_to_pay",
        "label_en": "Pressure applied to a payment demand",
        "label_ms": "Tekanan dikenakan pada permintaan bayaran",
        "description_en": "Urgency combined with a request for money, which is "
                          "how a renter is stopped from verifying anything.",
        "requires": (
            {"deadline_pressure", "competition_pressure", "rush_language"},
            _PAYMENT_ASK,
        ),
    },
    {
        "id": "absent_owner_payment",
        "label_en": "Absent owner asking for money",
        "label_ms": "Pemilik yang tiada meminta wang",
        "description_en": "Nobody will meet you, yet money is requested — the "
                          "unit may not exist or may belong to someone else.",
        "requires": (
            {"remote_owner", "key_courier", "meeting_avoidance", "viewing_denial"},
            _PAYMENT_ASK | {"personal_account", "third_party_account"},
        ),
    },
    {
        "id": "irregular_channel_payment",
        "label_en": "Payment through an untraceable channel",
        "label_ms": "Bayaran melalui saluran yang tidak boleh dikesan",
        "description_en": "Money is routed somewhere that cannot be reversed or "
                          "traced back to a verified owner.",
        "requires": (
            {"third_party_account", "non_bank_channel", "crypto_or_remittance"},
            _PAYMENT_ASK,
        ),
    },
)

# --------------------------------------------------------------------------
# Legitimacy signals — context only, never cancellation
# --------------------------------------------------------------------------

LEGIT_SIGNALS: tuple[dict, ...] = (
    {
        "id": "ren_number",
        "label_en": "A REN registration number was quoted",
        "note_en": "Verify it at lppeh.gov.my — REN numbers are sometimes copied "
                   "from real agents.",
        "patterns": (r"\bren\s*[-:]?\s*\d{4,6}\b", r"\bno\.?\s*ren\b"),
    },
    {
        "id": "registered_firm",
        "label_en": "A registered agency was named",
        "note_en": "Check the firm number against the agency's public listing.",
        "patterns": (r"\be\s*\(\s*\d\s*\)\s*\d{3,}", r"\bsdn\.?\s*bhd\b",
                     r"\bproperties?\s+sdn\b"),
    },
    {
        "id": "viewing_first",
        "label_en": "A viewing was offered before any payment",
        "note_en": "The strongest single sign of a genuine listing.",
        "patterns": (
            r"\b(?:boleh|can)\s+(?:datang\s+)?(?:view|viewing|tengok)\s+"
            r"(?:dulu|first|before)\b",
            r"\bview\s+(?:the\s+unit\s+)?(?:first|before\s+(?:you\s+)?pay)\b",
            r"\bbayar\s+(?:selepas|lepas)\s+(?:view|tengok|sign)\b",
        ),
    },
    {
        "id": "formal_documents",
        "label_en": "Ownership or tenancy documents were mentioned",
        "note_en": "Ask to see them; documents can be fabricated.",
        "patterns": (r"\bgeran\b", r"\bcukai\s+(?:taksiran|pintu)\b",
                     r"\btenancy\s+agreement\b", r"\bsurat\s+perjanjian\b"),
    },
    {
        "id": "stamping_mentioned",
        "label_en": "Stamping of the agreement was mentioned",
        "note_en": "A stamped tenancy is enforceable; ask for the stamped copy.",
        "patterns": (r"\bsetem\b", r"\bstamping\b", r"\bstamp\s+duty\b",
                     r"\blhdn\b"),
    },
    {
        "id": "company_account",
        "label_en": "Payment to a company account",
        "note_en": "Better than a personal account, but confirm the company is "
                   "the agency you are dealing with.",
        "patterns": (r"\bakaun\s+syarikat\b", r"\bcompany\s+account\b"),
    },
    # ------------------------------------------------------------------------
    # The six above were written for Malay, owner-direct, document-based
    # letting, and not one of them fired on a real English, agent-brokered,
    # platform-mediated conversation that was plainly legitimate. The signals
    # below cover that form. They were written after reading that conversation
    # (data/samples/legit_*), so layer 1's result on it is no longer a clean
    # test — only the sealed held-out set is.
    # ------------------------------------------------------------------------
    {
        "id": "viewing_arranged",
        "label_en": "A viewing was arranged",
        "note_en": "Arranging to see the unit in person is the strongest sign "
                   "of a genuine listing — provided the viewing happens before "
                   "any money is paid.",
        "patterns": (
            r"\b(?:plan|want|going)\s+to\s+(?:visit|view|see)\b",
            r"\b(?:i'?m|i\s+am)\s+available\s+(?:at|on|either)\b",
            r"\b(?:come|drop\s+by)\s+(?:and\s+)?(?:view|see|look)\b",
            r"\b(?:boleh|nak)\s+datang\s+(?:tengok|view|lawat)\b",
            r"\b(?:jumpa|meet)\s+(?:kat|at|di)\s+(?:unit|rumah|lobby|bawah)\b",
            r"\bview(?:ing)?\s+(?:on|this|next)\s+\w+",
        ),
    },
    {
        "id": "in_person_handover",
        "label_en": "Keys handed over in person",
        "note_en": "The opposite of keys by courier: someone who meets you to "
                   "hand over keys can be verified.",
        "patterns": (
            r"\bhand\s*over\s+(?:the\s+)?keys?\b",
            r"\bhandover\s+(?:the\s+)?keys?\b",
            r"\bkeys?\s+(?:in\s+person|handover)\b",
            r"\bserah\s+kunci\b",
            r"\bjumpa\b[^.!?\n]{0,40}\bkunci\b",
            r"\bmeet\b[^.!?\n]{0,40}\bkeys?\b",
        ),
    },
    {
        "id": "payment_at_handover",
        "label_en": "Payment tied to signing or handover",
        "note_en": "Paying at the signing or the key handover, after seeing the "
                   "unit, is the inverse of the pay-before-viewing scam.",
        "patterns": (
            r"\bsettle\s+(?:the\s+)?balance\b",
            r"\bpay\w*\s+(?:at|on|upon|during)\s+(?:the\s+)?(?:signing|handover)\b",
            r"\bbayar\s+(?:masa|semasa|selepas|lepas)\s+(?:sign|tengok|view|jumpa)\b",
            r"\bpaid\s+(?:at|on|upon)\s+(?:signing|handover)\b",
        ),
    },
    {
        "id": "platform_agreement",
        "label_en": "A written agreement through a platform or agency",
        "note_en": "An agreement issued through a named platform leaves a record "
                   "outside the chat. Confirm the platform is the real one.",
        "patterns": (
            r"\be-?agreement\b",
            r"\b(?:sign|check|read|review)\s+(?:and\s+sign\s+)?(?:the\s+)?agreement\b",
            r"\bagreement\s+is\s+ready\b",
            r"\bsigning\s+process\b",
            r"\b(?:ibilik|iproperty|propertyguru|speedhome|mudah)\b",
        ),
    },
)

_LEGIT_COMPILED = {
    signal["id"]: [re.compile(p, re.IGNORECASE) for p in signal["patterns"]]
    for signal in LEGIT_SIGNALS
}
_LEGIT_BY_ID = {signal["id"]: signal for signal in LEGIT_SIGNALS}


# --------------------------------------------------------------------------
# Exception handling
# --------------------------------------------------------------------------

def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence (or line) a match sits in."""
    left = max(
        text.rfind(".", 0, start), text.rfind("!", 0, start),
        text.rfind("?", 0, start), text.rfind("\n", 0, start),
    )
    right = min(
        [pos for pos in (
            text.find(".", end), text.find("!", end),
            text.find("?", end), text.find("\n", end),
        ) if pos != -1] or [len(text)]
    )
    return text[left + 1:right + 1]


def _suppression_reason(text: str, start: int, end: int, rule: Rule) -> str | None:
    """Why this match should not count, or None if it stands."""
    if not rule.exceptions:
        return None
    sentence = _sentence_around(text, start, end)

    if "negation" in rule.exceptions:
        # Only a cue *before* the match negates it: "jangan bayar dulu" is
        # advice, while "bayar dulu, jangan lambat" is two separate demands.
        if _NEGATION.search(text[max(0, start - 60):start]):
            return "negation"

    if "question" in rule.exceptions and sentence.rstrip().endswith("?"):
        return "question"

    if "timing" in rule.exceptions and _TIMING.search(sentence):
        return "timing"

    return None


def _speaker_for(text: str, start: int) -> str | None:
    """Who said it, if the transcript carries speaker prefixes."""
    line_start = text.rfind("\n", 0, start) + 1
    head = text[line_start:line_start + 40]
    match = re.match(
        r"\s*(renter|owner|pemilik|penyewa|agent|ejen)\s*:", head, re.IGNORECASE
    )
    return match.group(1).lower() if match else None


def _redact(snippet: str) -> str:
    for name in _REDACT:
        snippet = _ENTITY_PATTERNS[name].sub(f"[{name} redacted]", snippet)
    return snippet


def _snippet(text: str, start: int, end: int, width: int = 90) -> str:
    left = max(0, start - width // 3)
    right = min(len(text), end + width // 2)
    piece = text[left:right].replace("\n", " ").strip()
    if left > 0:
        piece = "..." + piece
    if right < len(text):
        piece = piece + "..."
    return _redact(piece)


def extract_entities(text: str) -> dict[str, list[str]]:
    """Phone numbers, IC numbers, account numbers, amounts and links."""
    found = {}
    for name, pattern in _ENTITY_PATTERNS.items():
        hits = list(dict.fromkeys(match.group(0) for match in pattern.finditer(text)))
        if hits:
            found[name] = hits
    return found


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def analyse(text: str) -> dict:
    """Full layer-1 analysis of a conversation.

    Returns red_flags (ids), evidence (one entry per fired rule), patterns,
    legit_signals, suppressed (matches cancelled by an exception, for
    debugging), entities, clean_text and token_count.

    No score, band or weight is produced here. Severity orders the evidence for
    display; it is never summed.
    """
    text = text or ""
    evidence = []
    suppressed = []

    for rule in RULES:
        hit = None
        for pattern in rule.compiled:
            for match in pattern.finditer(text):
                reason = _suppression_reason(text, match.start(), match.end(), rule)
                if reason:
                    suppressed.append({
                        "id": rule.id,
                        "reason": reason,
                        "snippet": _snippet(text, match.start(), match.end()),
                    })
                    continue
                hit = match
                break
            if hit:
                break

        if hit:
            evidence.append({
                "id": rule.id,
                "category": rule.category,
                "severity": rule.severity,
                "label_en": rule.label_en,
                "label_ms": rule.label_ms,
                "advice_en": rule.advice_en,
                "advice_ms": rule.advice_ms,
                "snippet": _snippet(text, hit.start(), hit.end()),
                "speaker": _speaker_for(text, hit.start()),
                "sources": list(rule.sources),
            })

    evidence.sort(key=lambda item: SEVERITY_ORDER[item["severity"]])
    fired = {item["id"] for item in evidence}

    patterns = [
        {
            "id": rule["id"],
            "label_en": rule["label_en"],
            "label_ms": rule["label_ms"],
            "description_en": rule["description_en"],
            "triggered_by": sorted(
                flag for group in rule["requires"] for flag in (fired & group)
            ),
        }
        for rule in PATTERN_RULES
        if all(fired & group for group in rule["requires"])
    ]

    matched_legit = [
        {
            "id": signal_id,
            "label_en": _LEGIT_BY_ID[signal_id]["label_en"],
            "note_en": _LEGIT_BY_ID[signal_id]["note_en"],
        }
        for signal_id, compiled in _LEGIT_COMPILED.items()
        if any(pattern.search(text) for pattern in compiled)
    ]

    # Legitimacy language is what scammers imitate. Measured on the labelled
    # corpus, every legitimacy signal that fires at all fires MORE often on
    # scams than on genuine conversations — "company_account" on 23.1% of scams
    # and 0.0% of legitimate ones, because scammers say "transfer to the owner
    # company account". Presented next to a red flag, it would reassure a
    # quarter of scam victims.
    #
    # So a legitimacy signal only counts when no red flag fired. Alongside one
    # it is withheld (kept for debugging, never shown as reassurance). With this
    # rule company_account falls to 0.0% of scams. Even so, any legit signal
    # fires on 5.7% of legitimate chats and 5.4% of scams: these are prompts to
    # verify, not evidence of safety, and the notes say so.
    if fired:
        legit = []
        legit_withheld = [
            {**signal, "reason": "legitimacy language alongside red flags"}
            for signal in matched_legit
        ]
    else:
        legit = matched_legit
        legit_withheld = []

    return {
        "red_flags": [item["id"] for item in evidence],
        "evidence": evidence,
        "patterns": patterns,
        "legit_signals": legit,
        "legit_signals_withheld": legit_withheld,
        "suppressed": suppressed,
        "entities": extract_entities(text),
        "clean_text": _redact(text),
        "token_count": len(text.split()),
    }


def extract_red_flags(text: str) -> list[str]:
    """Rule ids that fired, ordered by severity then catalogue order.

    Thin wrapper over analyse() kept for layer 2 and the backend, which only
    need the ids.
    """
    return analyse(text)["red_flags"]
