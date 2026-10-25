"""Generate matched legitimate/scam conversation pairs to break a learned shortcut.

Why this exists
---------------
The deployed classifier scored a real, legitimate iBilik agent conversation at
0.9997. eval/shortcut_probe.py isolated the cause: adding ONE line of itemised
prices to a known-legitimate conversation moves it from 0.0006 to 0.9492.
Length, terms and urgency do nothing on their own.

The training data explains it. In data/processed/random/train.csv
(eval/results/training_data_audit.json):

    P(SCAM | conversation lists >= 4 RM amounts) = 93.2%
    mean RM amounts: scam 3.4, legitimate 1.7

The synthetic scam templates itemise costs and the legitimate ones mention one
price. So "itemised breakdown -> scam" is right 93% of the time in training and
wrong for every real agent who sends a cost sheet — which is most of them.

The fix: minimal pairs
----------------------
Every pair is two conversations sharing an identical greeting, property details,
price breakdown and small talk, differing ONLY in the scam mechanics: whether
viewing happens before payment, how keys are handed over, whether there is
pressure, where the money goes. Price, length, language and writing style are
then identical across the two classes by construction, so they carry no
information and cannot be learned as a shortcut. What remains is the thing that
actually distinguishes a scam.

Length. The original corpus never exceeds 241 tokens; the real legitimate
conversation is 655-733 (eval/results/length_mismatch.json). The service now
scores long input in 512-token windows, so training must cover conversations up
to a window's length, and windows that start mid-conversation. Hence:

  * an "extended" profile with the long shared content real agents send
    (terms, promotions, penalties, house rules) — which is also exactly the
    content eval/shortcut_probe.py showed flipping a legitimate chat to SCAM,
    so it must appear in both twins;
  * mechanics inserted at a random position, the same in both twins, rather
    than always at the end, where 512-token truncation would cut them off and
    where position alone would become a cue;
  * matched FRAGMENT pairs: both twins cut at the same line, mid-conversation,
    keeping the mechanics — what the second window of a long chat looks like.
    Same source_group as their parent pair, so a split never separates them.

Every conversation is kept under CHAR_CAP so no training example is truncated.

Held-out test pairs use a held-out FAMILY of mechanic phrasings. Holding out
whole pairs is not enough: every pair is assembled from the same sentence banks,
and in the first version 92 of the 93 distinct mechanic sentences in the test
split also appeared, word for word, in training — so pair accuracy rewarded
recognising a memorised sentence. Now two families exist:

  * "train"   — the banks below, used for every training pair;
  * "heldout" — different sentences for the same tactics (viewing refused,
                pay first, keys by courier, urgency, third-party account, and
                their legitimate counterparts), used only for test pairs.

The shared scaffolding (greeting, property questions, prices, terms, small
talk) is common to both families on purpose: it is identical in both twins, so
it carries no label information, and a test that also changed it would measure
two things at once. generate() refuses to write if any mechanic sentence of the
test split appears anywhere in the training split.

Kinds of row (column "kind"):
  full       the whole conversation, one legitimate and one scam twin
  fragment   both twins cut at the same line mid-conversation, keeping the
             mechanics — the shape of a later window
  truncated  both twins cut after the mechanics, before the goodbye
  prefix     ONE row, labelled LEGITIMATE: text before the twins diverge, which
             is identical in both and holds no scam behaviour. The service
             takes the highest-scoring window, so a window must mean "scam
             behaviour is in this text"; retrain run 1 scored such windows
             0.8-0.9 because nothing in training said otherwise.
  core       ONE row, labelled SCAM: as many lines as its prefix, from the scam
             twin, including its first scam line — so length stays uninformative

Each row carries:
  pair_id       one twin pair ("MPnnnn", "-F" fragment, "-T" truncated) or one
                prefix row ("-P")
  source_group  the parent pair, shared by a pair and its fragment pair, so a
                split never separates them
  family        "train" or "heldout"

    python training/make_minimal_pairs.py --pairs 480 --seed 7

Writes data/processed/augmented/minimal_pairs_train.csv and _test.csv.
"""
import argparse
import csv
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "..", "data", "processed", "augmented")

# ---------------------------------------------------------------------------
# Shared building blocks — appear identically in BOTH twins of a pair
# ---------------------------------------------------------------------------

AREAS = [
    "Cheras", "Kajang", "Subang Jaya", "Shah Alam", "Petaling Jaya", "Puchong",
    "Bangi", "Setia Alam", "Cyberjaya", "Kepong", "Wangsa Maju", "Ampang",
    "Seri Kembangan", "Klang", "Sentul", "Bukit Jalil", "Rawang", "Semenyih",
    "Nilai", "Johor Bahru", "Georgetown", "Ipoh", "Seremban", "Melaka",
]
PLACES = {
    "ms": ["bilik master", "bilik single", "bilik medium", "rumah teres",
           "apartment", "kondo", "studio", "rumah flat", "rumah pangsa"],
    "en": ["master room", "single room", "medium room", "terrace house",
           "apartment", "condo", "studio", "flat", "serviced apartment"],
}

GREETING = {
    "ms": [
        "salam, {place} kat {area} tu masih ada lagi ke?",
        "hi, nak tanya {place} area {area} ada kosong lagi?",
        "assalamualaikum, saya berminat dengan {place} di {area}",
        "hai, {place} {area} yang iklan tu available lagi tak?",
        "salam tuan, {place} di {area} masih boleh sewa?",
    ],
    "en": [
        "Hi, is the {place} in {area} still available?",
        "Hello, I saw your listing for the {place} in {area}.",
        "Hi there, I'm interested in the {place} at {area}.",
        "Good evening, is the {place} in {area} still for rent?",
        "Hi, just checking if the {place} in {area} is taken.",
    ],
    "mix": [
        "hi, {place} kat {area} tu still available ke?",
        "salam, nak tanya pasal the {place} in {area}",
        "hello, {place} {area} masih ada? I'm interested",
        "hi kak, the {place} kat {area} tu boleh sewa lagi?",
    ],
}
AVAILABLE = {
    "ms": ["ada lagi. nak masuk bila?", "masih kosong. duduk berapa orang?",
           "ya masih ada. kerja area mana?", "ada, belum ada orang ambil lagi",
           "masih available. tarikh masuk bila ye?"],
    "en": ["Yes it is. When are you looking to move in?",
           "Still available. How many people will stay?",
           "Yes, it's free. Where do you work?",
           "It is, nobody has taken it yet.",
           "Yes. What move-in date are you thinking of?"],
    "mix": ["ada lagi. when nak masuk?", "still available. berapa orang?",
            "yes masih kosong. kerja area mana?", "ada lagi, belum taken"],
}
PROPERTY_Q = {
    "ms": ["fully furnished ke?", "ada parking tak?", "boleh masak tak?",
           "ada aircond?", "dekat dengan LRT tak?", "air dan elektrik macam mana?"],
    "en": ["Is it fully furnished?", "Is there parking?", "Is cooking allowed?",
           "Does it have aircond?", "Is it near the LRT?", "How do utilities work?"],
    "mix": ["fully furnished ke?", "ada parking tak?", "boleh masak ke?",
            "aircond ada?", "near LRT tak?", "utilities macam mana?"],
}
PROPERTY_A = {
    "ms": ["ya fully furnished, ada katil dan almari.", "ada satu parking.",
           "boleh masak ringan je.", "ada aircond setiap bilik.",
           "lima minit jalan kaki ke LRT.", "elektrik prepaid, air termasuk sewa."],
    "en": ["Yes, fully furnished with bed and wardrobe.", "There's one parking bay.",
           "Light cooking only.", "Every room has aircond.",
           "About five minutes' walk to the LRT.",
           "Electricity is prepaid, water is included."],
    "mix": ["yes fully furnished, ada bed dan wardrobe.", "ada one parking.",
            "light cooking only ya.", "aircond ada setiap room.",
            "5 minit walk ke LRT.", "elektrik prepaid, water included."],
}

# Itemised costs: the shortcut feature. In BOTH twins, at matched rates.
PRICE_BLOCK = {
    "ms": [
        "sewa RM{rent} sebulan. deposit RM{dep}, deposit utiliti RM{util}. total masuk RM{total}.",
        "Sewa bulanan RM{rent}\nDeposit 2 bulan RM{dep}\nUtiliti RM{util}\nJumlah masuk RM{total}",
        "harga RM{rent}/bulan. deposit RM{dep} + utiliti RM{util}. semua sekali RM{total}.",
    ],
    "en": [
        "Rent is RM{rent} a month. Deposit RM{dep}, utility deposit RM{util}. Total move-in RM{total}.",
        "Move-in breakdown:\nMonthly rental RM{rent}\nDeposit RM{dep}\nUtility deposit RM{util}\nTotal RM{total}",
        "RM{rent} monthly. Security deposit RM{dep} plus utility deposit RM{util}, RM{total} in total.",
    ],
    "mix": [
        "sewa RM{rent}/month. deposit RM{dep}, utility RM{util}. total masuk RM{total}.",
        "Monthly rental RM{rent}\nDeposit RM{dep}\nUtiliti RM{util}\nTotal masuk RM{total}",
    ],
}
CHATTER = {
    "ms": [("boleh bawa kawan duduk sekali?", "boleh, maksimum dua orang."),
           ("ada washing machine?", "ada, share dengan bilik lain."),
           ("wifi ada tak?", "ada, termasuk dalam sewa."),
           ("kawasan ni selamat tak?", "selamat, ada guard 24 jam."),
           ("boleh bela kucing?", "maaf, tak boleh bela haiwan."),
           ("ada kedai makan dekat?", "banyak, depan rumah je."),
           ("orang lain dalam rumah kerja apa?", "semua kerja pejabat, senyap."),
           ("minimum sewa berapa lama?", "minimum setahun.")],
    "en": [("Can I stay with a friend?", "Yes, maximum two people."),
           ("Is there a washing machine?", "Yes, shared with the other rooms."),
           ("Is wifi included?", "Yes, it's part of the rent."),
           ("Is the area safe?", "Yes, there's 24-hour security."),
           ("Are pets allowed?", "Sorry, no pets."),
           ("Any food nearby?", "Plenty, right in front of the building."),
           ("Who else lives there?", "All working adults, quite quiet."),
           ("What's the minimum tenancy?", "Minimum twelve months.")],
    "mix": [("boleh stay dengan kawan?", "boleh, max dua orang."),
            ("washing machine ada?", "ada, shared."),
            ("wifi included ke?", "yes termasuk dalam sewa."),
            ("area ni safe tak?", "safe, ada guard 24 jam."),
            ("boleh bela kucing?", "sorry, no pets."),
            ("minimum tenancy berapa lama?", "minimum setahun ya.")],
}

# Long agent boilerplate: promotions, terms and penalties. The real legitimate
# conversation carried all three, and eval/shortcut_probe.py showed prices plus
# terms alone scoring a legitimate chat 0.9992. In BOTH twins.
TERMS_BLOCK = {
    "ms": [
        "Terma & syarat: deposit 1 bulan. Sewa minimum 12 bulan. Tamat awal dikenakan penalti RM{pen}. Unit terhad.",
        "PROMOSI bulan ni: diskaun 50% sewa bulan pertama. Minimum sewa 12 bulan. Penalti tamat awal RM{pen}. Unit terhad, book awal!",
        "Syarat sewa: minimum 12 bulan, deposit 1 bulan + sewa pendahuluan 1 bulan. Yuran masuk RM{fee} termasuk agreement dan cuci bilik. Keluar sebelum 12 bulan deposit hangus.",
    ],
    "en": [
        "Terms & Conditions: 1 month deposit required. Minimum 12-month tenancy. Early termination may incur a RM{pen} penalty. Limited units available.",
        "PROMO this month: 50% off your first month's rental. Minimum 12-month tenancy required. Early termination penalty RM{pen}. Limited units, secure yours today!",
        "Tenancy terms: minimum 12 months, 1 month deposit plus 1 month advance rental. Move-in fee RM{fee} covers the agreement fee and cleaning upon move-out. Leaving before 12 months forfeits the deposit.",
    ],
    "mix": [
        "Terms: deposit 1 month. minimum tenancy 12 bulan. early termination penalty RM{pen}. unit terhad ya.",
        "PROMO bulan ni: 50% off first month rental. minimum 12 bulan. penalty RM{pen} kalau keluar awal. limited units!",
    ],
}
HOUSE_RULES = {
    "ms": ["Peraturan rumah: tak boleh merokok dalam rumah, tiada haiwan, pelawat sampai 11 malam, jaga kebersihan.",
           "Peraturan: senyap lepas 11 malam, tetamu bermalam kena bagitahu dulu, masak ringan sahaja, buang sampah setiap petang."],
    "en": ["House rules: no smoking indoors, no pets, visitors until 11pm, keep the common areas clean.",
           "Rules: quiet hours after 11pm, no overnight guests without notice, light cooking only, rubbish out every evening."],
    "mix": ["house rules: no smoking dalam rumah, no pets, visitors sampai 11pm, jaga common area bersih ya."],
}
# Neutral back-and-forth about getting there and moving in. In BOTH twins.
LOGISTICS = {
    "ms": [("saya dari Kelantan, jauh tak dari terminal bas?", "lebih kurang 20 minit naik Grab."),
           ("boleh masuk awal sikit?", "boleh rasanya, saya confirm dengan penyewa sekarang dulu."),
           ("bilik menghadap jalan ke?", "tak, menghadap belakang, senyap."),
           ("ada lif?", "ada, dua lif."),
           ("boleh bawa perabot sendiri?", "boleh, bagitahu awal supaya saya alihkan katil.")],
    "en": [("I'm travelling from Kelantan, is it far from the bus terminal?", "About 20 minutes by Grab."),
           ("Can I move in a bit earlier?", "Should be fine, let me confirm with the current tenant."),
           ("Is the room facing the road?", "No, it faces the back, quite quiet."),
           ("Is there a lift?", "Yes, two lifts."),
           ("Can I bring my own furniture?", "Yes, just tell me early so I can remove the bed.")],
    "mix": [("saya from Kelantan, jauh tak dari bus terminal?", "around 20 minit naik Grab."),
            ("boleh move in awal sikit?", "should be ok, nanti saya confirm."),
            ("room facing road ke?", "tak, facing belakang, quiet."),
            ("lif ada?", "ada, two lifts.")],
}

# ---------------------------------------------------------------------------
# Mechanics — the ONLY thing that differs between twins
# ---------------------------------------------------------------------------

LEGIT_VIEWING = {
    "ms": [("boleh saya tengok rumah dulu?", "boleh, datang Sabtu ni pukul 11 pagi. saya tunggu kat bawah."),
           ("bila boleh view?", "hujung minggu ni boleh. saya bukakan rumah untuk awak tengok."),
           ("nak tengok dulu sebelum decide", "sure, bila free? saya boleh jumpa kat unit.")],
    "en": [("Can I view it first?", "Of course. Saturday at 11am works, I'll meet you there."),
           ("When can I come and see it?", "This weekend. I'll open the unit so you can look around."),
           ("I'd like to see it before deciding.", "No problem, when are you free? I'll meet you at the unit.")],
    "mix": [("boleh view dulu?", "boleh, Saturday 11am ok? I'll meet you kat unit."),
            ("bila boleh tengok?", "this weekend boleh. saya open the unit for you.")],
}
# Payment options are ALIGNED with SCAM_PAYMENT: option i here and option i
# there mention the same number of RM amounts. An earlier version let only the
# scam side name a price ("booking RM{book} dulu"), so every scam twin carried
# one extra amount — and "one more RM = scam" is the very shortcut these pairs
# exist to remove. training/audit_training_data.py caught it.
LEGIT_PAYMENT = {
    "ms": [("bila kena bayar?", "bayar masa sign agreement lepas awak tengok rumah."),
           ("deposit bayar macam mana?", "bayar semasa kita jumpa untuk sign perjanjian, bukan sebelum."),
           ("perlu bayar booking?", "tak perlu booking. deposit RM{dep} bayar masa sign lepas tengok.")],
    "en": [("When do I pay?", "You pay when we sign the agreement, after you've seen the place."),
           ("How does the deposit work?", "Deposit is paid at the signing, not before."),
           ("Do I need to pay a booking fee?", "No booking fee. The RM{dep} deposit is paid at signing, after viewing.")],
    "mix": [("bila kena bayar?", "pay masa sign agreement, after you view."),
            ("need booking fee ke?", "no booking. deposit RM{dep} pay masa sign after viewing.")],
}
LEGIT_KEYS = {
    "ms": ["kunci saya serah sendiri masa awak masuk.", "kita jumpa kat unit untuk serah kunci dan check keadaan rumah.",
           "masa sign nanti saya bagi kunci dan access card terus."],
    "en": ["I'll hand you the keys in person on move-in day.",
           "We'll meet at the unit to hand over keys and check the condition together.",
           "At the signing I'll give you the keys and access card directly."],
    "mix": ["kunci I hand over sendiri masa move in.", "kita jumpa kat unit untuk handover keys."],
}
LEGIT_AGREEMENT = {
    "ms": ["perjanjian sewa kita buat bertulis dan setem.", "agreement saya sediakan, awak baca dulu sebelum sign.",
           "sign agreement kat pejabat agensi."],
    "en": ["We'll do a written tenancy agreement and get it stamped.",
           "I'll send the agreement for you to read before signing.",
           "We sign the agreement at the agency office."],
    "mix": ["agreement kita buat bertulis dan stamp.", "I'll send agreement, baca dulu before sign."],
}

SCAM_VIEWING = {
    "ms": [("boleh saya tengok rumah dulu?", "maaf saya outstation sekarang, tak boleh bukakan rumah."),
           ("bila boleh view?", "saya kerja luar negara, tak dapat tunjuk rumah buat masa ni."),
           ("nak tengok dulu sebelum decide", "tak boleh view dulu, kena lock dulu baru boleh tengok.")],
    "en": [("Can I view it first?", "Sorry, I'm overseas right now so I can't open the unit."),
           ("When can I come and see it?", "I'm working in Singapore, viewing isn't possible at the moment."),
           ("I'd like to see it before deciding.", "You'll need to reserve it first, then we can arrange a viewing.")],
    "mix": [("boleh view dulu?", "sorry saya overseas, can't open the unit."),
            ("bila boleh tengok?", "tak boleh view dulu, kena reserve first.")],
}
SCAM_PAYMENT = {
    "ms": [("bila kena bayar?", "kena bayar booking dulu hari ni untuk lock bilik."),
           ("deposit bayar macam mana?", "transfer deposit dulu, lepas tu baru boleh tengok."),
           ("perlu bayar booking?", "ya, kena bayar booking RM{book} dulu baru saya simpan untuk awak.")],
    "en": [("When do I pay?", "You'll need to pay the booking fee today to lock the room."),
           ("How does the deposit work?", "Transfer the deposit first, then I'll arrange the viewing."),
           ("Do I need to pay a booking fee?", "Yes, RM{book} booking first and I'll hold it for you.")],
    "mix": [("bila kena bayar?", "kena bayar booking dulu today to lock the room."),
            ("need booking fee ke?", "yes, RM{book} booking dulu then saya hold for you.")],
}
SCAM_EXTRA = {
    "ms": ["ramai orang tengah tanya, kena cepat.", "saya pos kunci lepas awak transfer.",
           "kalau tak jadi saya refund balik sepenuhnya.", "bayar sebelum pukul 9 malam ni ya.",
           "saya takde akaun bank, guna TNG je.", "transfer ke akaun adik saya ya."],
    "en": ["Many people are asking, you'll need to be quick.", "I'll courier the keys after you transfer.",
           "If it's not suitable I'll refund you in full.", "Please pay before 9pm tonight.",
           "I don't have a bank account, just use TNG.", "Transfer to my brother's account please."],
    "mix": ["ramai tanya, kena cepat ya.", "I'll post the keys lepas you transfer.",
            "kalau tak jadi saya refund balik full.", "pay before 9pm tonight ya."],
}

# ---------------------------------------------------------------------------
# Held-out family — the same tactics in different words, for TEST pairs only.
# Same shapes as the train banks: viewing and payment questions are aligned by
# index across legit and scam, and payment option i names the same number of RM
# amounts on both sides.
# ---------------------------------------------------------------------------

HELDOUT_LEGIT_VIEWING = {
    "ms": [("boleh jenguk unit dulu sebelum setuju?", "boleh je, petang Ahad saya ada kat sana, datang la tengok."),
           ("saya nak survey rumah dulu boleh?", "boleh, bagitahu masa, saya tunjukkan semua bilik.")],
    "en": [("Would it be possible to look around before I commit?", "Sure, I'm there Sunday afternoon, come by and have a look."),
           ("Could we arrange a viewing?", "Yes, tell me a time that suits you and I'll show you every room.")],
    "mix": [("boleh I tengok unit dulu before commit?", "boleh, Sunday petang I ada kat sana, come and see."),
            ("nak arrange viewing boleh?", "boleh, bagi masa you free, I tunjuk semua bilik.")],
}
HELDOUT_SCAM_VIEWING = {
    "ms": [("boleh jenguk unit dulu sebelum setuju?", "tak sempat, saya duduk Sabah sekarang, kunci pun takde dengan saya."),
           ("saya nak survey rumah dulu boleh?", "rumah berkunci, penyewa lama belum keluar, tak boleh masuk tengok.")],
    "en": [("Would it be possible to look around before I commit?", "Not really, I'm based in Sabah and nobody here has the keys."),
           ("Could we arrange a viewing?", "The unit is locked until the old tenant leaves, so no viewings for now.")],
    "mix": [("boleh I tengok unit dulu before commit?", "tak boleh, I duduk Sabah, keys pun takde dengan I."),
            ("nak arrange viewing boleh?", "unit locked sampai old tenant keluar, no viewing for now.")],
}
HELDOUT_LEGIT_PAYMENT = {
    "ms": [("bila saya perlu bayar deposit?", "deposit dibayar hari tandatangan perjanjian, lepas awak puas hati dengan rumah."),
           ("ada yuran tempahan?", "takde yuran tempahan. deposit RM{dep} dibayar bila sign, lepas viewing.")],
    "en": [("When is the deposit due?", "The deposit is due on the day we sign, once you're happy with the place."),
           ("Is there a holding fee?", "No holding fee. The RM{dep} deposit is due at signing, after the viewing.")],
    "mix": [("bila deposit due?", "deposit bayar on signing day, lepas you puas hati dengan rumah."),
            ("ada holding fee?", "takde holding fee. deposit RM{dep} bayar masa sign, after viewing.")],
}
HELDOUT_SCAM_PAYMENT = {
    "ms": [("bila saya perlu bayar deposit?", "deposit kena masuk hari ni juga, kalau tak saya bagi orang lain."),
           ("ada yuran tempahan?", "ada, yuran tempahan RM{book} kena bank-in malam ni untuk simpan unit.")],
    "en": [("When is the deposit due?", "The deposit has to be in today, otherwise I'll give it to someone else."),
           ("Is there a holding fee?", "Yes, a RM{book} holding fee has to be banked in tonight to keep the unit.")],
    "mix": [("bila deposit due?", "deposit kena masuk today, kalau tak I bagi orang lain."),
            ("ada holding fee?", "ada, RM{book} holding fee kena bank-in tonight untuk hold unit.")],
}
HELDOUT_LEGIT_KEYS = {
    "ms": ["kunci dan kad akses saya serahkan depan-depan hari pindah.",
           "hari masuk kita jumpa, saya serah kunci dan kita periksa inventori sama-sama."],
    "en": ["You'll get the keys and access card from me in person on the day.",
           "On move-in day we'll meet, I'll hand over the keys and we'll go through the inventory together."],
    "mix": ["keys dan access card I serah by hand on move-in day.",
            "move in day kita jumpa, I handover keys, check inventory sama-sama."],
}
HELDOUT_LEGIT_AGREEMENT = {
    "ms": ["perjanjian sewa akan disetem di LHDN, satu salinan untuk awak.",
           "draf perjanjian saya emel dulu, awak semak sebelum tandatangan."],
    "en": ["The tenancy agreement gets stamped at LHDN and you keep a copy.",
           "I'll email the draft agreement first so you can check it before signing."],
    "mix": ["agreement akan stamp kat LHDN, you simpan satu copy.",
            "draft agreement I emel dulu, you check before sign."],
}
HELDOUT_SCAM_EXTRA = {
    "ms": ["ada tiga orang lagi nak unit ni, siapa bayar dulu dia dapat.",
           "kunci saya hantar guna Poslaju lepas duit masuk.",
           "jangan risau, kalau tak berkenan duit saya pulangkan semua.",
           "kena selesai sebelum tengah malam ni ya.",
           "akaun saya ada masalah, bank-in ke akaun kawan saya.",
           "bayar guna DuitNow je, senang."],
    "en": ["Three others want this unit, whoever pays first gets it.",
           "I'll send the keys by Poslaju once the money is in.",
           "Don't worry, if you don't like it I'll return every sen.",
           "This needs to be settled before midnight.",
           "My account has an issue, bank in to my friend's account instead.",
           "Just pay by DuitNow, it's easier."],
    "mix": ["ada 3 orang lagi nak, first pay first get.",
            "keys I hantar by Poslaju lepas duit masuk.",
            "don't worry, kalau tak suka I return semua.",
            "kena settle before midnight ya."],
}

FAMILIES = {
    "train": {
        "legit_viewing": LEGIT_VIEWING, "scam_viewing": SCAM_VIEWING,
        "legit_payment": LEGIT_PAYMENT, "scam_payment": SCAM_PAYMENT,
        "legit_keys": LEGIT_KEYS, "legit_agreement": LEGIT_AGREEMENT,
        "scam_extra": SCAM_EXTRA,
    },
    "heldout": {
        "legit_viewing": HELDOUT_LEGIT_VIEWING, "scam_viewing": HELDOUT_SCAM_VIEWING,
        "legit_payment": HELDOUT_LEGIT_PAYMENT, "scam_payment": HELDOUT_SCAM_PAYMENT,
        "legit_keys": HELDOUT_LEGIT_KEYS, "legit_agreement": HELDOUT_LEGIT_AGREEMENT,
        "scam_extra": HELDOUT_SCAM_EXTRA,
    },
}


def _check_family(name, banks):
    """Twins must ask the same question and name the same number of amounts."""
    for legit, scam in (("legit_viewing", "scam_viewing"), ("legit_payment", "scam_payment")):
        for lang in banks[legit]:
            left, right = banks[legit][lang], banks[scam][lang]
            assert len(left) == len(right), f"{name}/{legit}/{lang}: unequal options"
            for (q1, a1), (q2, a2) in zip(left, right):
                assert q1 == q2, f"{name}/{legit}/{lang}: questions not aligned: {q1!r}"
                assert a1.count("RM{") == a2.count("RM{"), f"{name}/{legit}/{lang}: RM counts differ"


for _name, _banks in FAMILIES.items():
    _check_family(_name, _banks)

CLOSING = {
    "ms": [("ok baik, terima kasih", "sama-sama"), ("baik, saya fikir dulu", "ok, bagitahu ya")],
    "en": [("Okay, thank you", "You're welcome"), ("Alright, let me think about it", "Sure, let me know")],
    "mix": [("ok noted, thanks", "sama-sama"), ("alright, saya fikir dulu", "ok, let me know")],
}


def _pick(rng, bank, lang):
    return rng.choice(bank.get(lang) or bank["en"])


# Longest a generated conversation may be. ~1600 characters is ~450 XLM-R
# tokens on this text, under the 510 a 512 window holds, so no example is ever
# truncated and no scam twin can lose its mechanics to truncation.
# eval/length_mismatch.py checks the result.
CHAR_CAP = 1600


def _render(lines):
    return "\n".join(f"{speaker}: {text}" for speaker, text in lines)


def make_pair(rng, pair_id, family="train"):
    banks = FAMILIES[family]
    lang = rng.choices(["ms", "en", "mix"], weights=[0.35, 0.35, 0.30])[0]
    place_lang = "en" if lang == "en" else "ms"
    area = rng.choice(AREAS)
    place = rng.choice(PLACES[place_lang])
    rent = rng.choice([350, 450, 500, 600, 750, 900, 1200, 1500, 1800, 2200])
    dep = rent * rng.choice([1, 2])
    util = rng.choice([50, 100, 150, 200, 300])
    book = rng.choice([200, 300, 500, 800])
    fill = dict(area=area, place=place, rent=rent, dep=dep, util=util,
                total=rent + dep + util, book=book,
                pen=rng.choice([300, 500, 600, 1000]), fee=rng.choice([100, 200, 300]))

    # Length profile. "extended" is the size of one 512-token window: real
    # conversations are longer still and are scored window by window.
    profile = rng.choices(["short", "medium", "long", "extended"],
                          weights=[0.20, 0.25, 0.25, 0.30])[0]
    n_chatter = {"short": 0, "medium": rng.randint(1, 3), "long": rng.randint(3, 5),
                 "extended": rng.randint(5, 8)}[profile]
    with_prices = rng.random() < 0.75   # prices common, in BOTH classes
    with_terms = profile == "extended" or (profile == "long" and rng.random() < 0.5)
    with_rules = profile == "extended" and rng.random() < 0.6

    # Shared content, as units that keep a question with its answer. Every unit
    # appears identically in both twins.
    opener = [("Renter", _pick(rng, GREETING, lang).format(**fill)),
              ("Owner", _pick(rng, AVAILABLE, lang))]
    q_index = rng.randrange(len(PROPERTY_Q.get(lang, PROPERTY_Q["en"])))
    fixed = [[("Renter", PROPERTY_Q.get(lang, PROPERTY_Q["en"])[q_index]),
              ("Owner", PROPERTY_A.get(lang, PROPERTY_A["en"])[q_index])]]
    if with_prices:
        fixed.append([("Owner", _pick(rng, PRICE_BLOCK, lang).format(**fill))])
    if with_terms:
        fixed.append([("Owner", _pick(rng, TERMS_BLOCK, lang).format(**fill))])
    if with_rules:
        fixed.append([("Owner", _pick(rng, HOUSE_RULES, lang))])
    small_talk = (CHATTER.get(lang, CHATTER["en"])
                  + (LOGISTICS.get(lang, LOGISTICS["en"]) if profile == "extended" else []))
    droppable = [[("Renter", q), ("Owner", a)]
                 for q, a in rng.sample(small_talk, k=min(n_chatter, len(small_talk)))]

    closing = _pick(rng, CLOSING, lang)
    closing_lines = [("Renter", closing[0]), ("Owner", closing[1])]

    def bank(key):
        return banks[key].get(lang) or banks[key]["en"]

    # Legitimate mechanics: view first, pay at signing, keys in person. The
    # viewing and payment QUESTIONS are drawn once and shared by both twins —
    # an earlier version drew them separately, so twins could differ in a line
    # that is not a mechanic.
    view_index = rng.randrange(len(bank("legit_viewing")))
    view_q, view_a = bank("legit_viewing")[view_index]
    pay_index = rng.randrange(len(bank("legit_payment")))
    pay_q, pay_a = bank("legit_payment")[pay_index]
    legit_tail = []
    if profile != "short":
        legit_tail.append(("Owner", rng.choice(bank("legit_keys"))))
    if profile in ("long", "extended"):
        legit_tail.append(("Owner", rng.choice(bank("legit_agreement"))))

    # Scam mechanics: same questions, the answers turn into the scam. The tail
    # is matched line for line, so length is uninformative.
    s_view_q, s_view_a = bank("scam_viewing")[view_index]
    s_pay_q, s_pay_a = bank("scam_payment")[pay_index]
    scam_tail = [("Owner", line) for line in rng.sample(bank("scam_extra"), k=len(legit_tail))]

    mechanics = {
        "LEGITIMATE": ([("Renter", view_q), ("Owner", view_a)],
                       [("Renter", pay_q), ("Owner", pay_a.format(**fill))] + legit_tail),
        "SCAM": ([("Renter", s_view_q), ("Owner", s_view_a)],
                 [("Renter", s_pay_q), ("Owner", s_pay_a.format(**fill))] + scam_tail),
    }

    # Where the mechanics go, as fractions, so the same draw still applies
    # after small talk is dropped to fit CHAR_CAP. Viewing comes before payment.
    order = rng.sample(fixed + droppable, k=len(fixed) + len(droppable))
    at_view, at_pay = sorted((rng.random(), rng.random()))

    def build(units):
        view_i = round(at_view * len(units))
        pay_i = max(view_i, round(at_pay * len(units)))
        twins, starts = {}, {}
        for label, (viewing, payment) in mechanics.items():
            blocks = list(units)
            blocks.insert(pay_i, payment)
            blocks.insert(view_i, viewing)
            lines = list(opener)
            first_mechanic = None
            for index, block in enumerate(blocks):
                if index == view_i:
                    first_mechanic = len(lines)
                lines += block
            twins[label] = lines + closing_lines
            starts[label] = first_mechanic
        return twins, starts

    twins, starts = build(order)
    while max(len(_render(t)) for t in twins.values()) > CHAR_CAP:
        removable = [u for u in order if u in droppable]
        if not removable:
            break
        order.remove(removable[-1])
        twins, starts = build(order)

    group = f"MP{pair_id:04d}"
    meta = {"origin": "minimal_pair", "source_group": group, "family": family,
            "lang": lang, "profile": profile, "with_prices": with_prices}
    rows = [{"text": _render(twins[label]), "label": label, "kind": "full",
             "pair_id": group, **meta}
            for label in ("LEGITIMATE", "SCAM")]

    # A matched fragment: both twins cut at the same line, after the opener and
    # before the first mechanic — the shape of a later 512-token window.
    first = starts["LEGITIMATE"]
    if profile == "extended" and first is not None and first > 3 and rng.random() < 0.6:
        cut = rng.randint(3, first)
        rows += [{"text": _render(twins[label][cut:]), "label": label,
                  "kind": "fragment", "pair_id": f"{group}-F", **meta}
                 for label in ("LEGITIMATE", "SCAM")]

    # Cuts that give the label a meaning at the level of a WINDOW. The service
    # scores a long chat in windows and takes the highest, so each window must
    # answer "is there scam behaviour in this text?" Retrain run 1 showed what
    # happens when training never says: a window of promotions, terms, prices
    # and viewing chat with nothing wrong in it scored 0.8-0.9, and a scam with
    # its mechanics removed scored 0.52 (eval/results/v3_run1_printout.txt).
    legit_lines, scam_lines = twins["LEGITIMATE"], twins["SCAM"]
    differ = [i for i, (a, b) in enumerate(zip(legit_lines, scam_lines)) if a != b]
    first_diff, last_diff = differ[0], differ[-1]

    # PREFIX: ends before the twins diverge, so it is the same text in both and
    # holds no scam behaviour - LEGITIMATE whichever conversation it came from.
    # One row, since both twins would give the identical text.
    if first_diff >= 3 and rng.random() < 0.5:
        begin = 0 if first_diff < 4 or rng.random() < 0.5 else rng.randint(1, first_diff - 3)
        end = rng.randint(begin + 3, first_diff)
        rows.append({"text": _render(legit_lines[begin:end]), "label": "LEGITIMATE",
                     "kind": "prefix", "pair_id": f"{group}-P", **meta})
        # CORE: the same number of lines from the scam twin, placed to include
        # its first scam line. Prefixes are short and all LEGITIMATE; without a
        # length-matched SCAM counterpart "short means legitimate" becomes a
        # shortcut (training/audit_training_data.py measured it at 8.5 points
        # over baseline before this was added).
        n = end - begin
        start = max(0, min(first_diff - rng.randint(0, n - 1), len(scam_lines) - n))
        rows.append({"text": _render(scam_lines[start:start + n]), "label": "SCAM",
                     "kind": "core", "pair_id": f"{group}-C", **meta})

    # TRUNCATED: both twins cut after the last mechanic and before the goodbye.
    # Every prefix ends abruptly; these make an abrupt ending occur in both
    # classes, so it cannot become the cue for LEGITIMATE.
    if rng.random() < 0.5:
        end = rng.randint(last_diff + 1, len(legit_lines) - 1)
        rows += [{"text": _render(twins[label][:end]), "label": label,
                  "kind": "truncated", "pair_id": f"{group}-T", **meta}
                 for label in ("LEGITIMATE", "SCAM")]
    return rows


FIELDS = ["text", "label", "kind", "pair_id", "source_group", "family", "origin",
          "lang", "profile", "with_prices"]


def _body(line):
    return line.split(": ", 1)[-1]


TWIN_KINDS = ("full", "fragment", "truncated")


def mechanic_lines(rows):
    """Lines where a pair's twins differ — the mechanics, both sides."""
    by_pair = {}
    for row in rows:
        if row["kind"] not in TWIN_KINDS:
            continue
        by_pair.setdefault(row["pair_id"], {})[row["label"]] = row["text"].split("\n")
    found = set()
    for twins in by_pair.values():
        for legit, scam in zip(twins["LEGITIMATE"], twins["SCAM"]):
            if legit != scam:
                found.update((_body(legit), _body(scam)))
    return found


def verify(train, test):
    """Refuse output that would let the pair test reward memorisation."""
    for name, rows in (("train", train), ("test", test)):
        counts = {}
        for row in rows:
            counts.setdefault(row["pair_id"], []).append(row["label"])
        for row in rows:
            labels = counts[row["pair_id"]]
            if row["kind"] in TWIN_KINDS:
                assert sorted(labels) == ["LEGITIMATE", "SCAM"], f"{name} {row['pair_id']}: {labels}"
            elif row["kind"] == "prefix":
                assert labels == ["LEGITIMATE"], f"{name} {row['pair_id']}: {labels}"
            else:
                assert row["kind"] == "core" and labels == ["SCAM"], f"{name} {row['pair_id']}: {labels}"
        # A prefix may only hold lines both twins share: no scam behaviour.
        full = {}
        for row in rows:
            if row["kind"] == "full":
                full.setdefault(row["source_group"], []).append(set(row["text"].split("\n")))
        for row in rows:
            if row["kind"] == "prefix":
                legit, scam = full[row["source_group"]]
                for line in row["text"].split("\n"):
                    assert line in legit and line in scam, f"{row['pair_id']}: {line!r}"
            if row["kind"] == "core":
                legit, scam = full[row["source_group"]]
                lines = row["text"].split("\n")
                assert all(line in scam for line in lines), row["pair_id"]
                assert any(line not in legit for line in lines), f"{row['pair_id']}: no scam line"
    train_lines = {_body(line) for row in train for line in row["text"].split("\n")}
    leaked = mechanic_lines(test) & train_lines
    assert not leaked, f"test mechanic sentences also in training: {sorted(leaked)[:5]}"
    assert {row["family"] for row in train} == {"train"}
    assert {row["family"] for row in test} == {"heldout"}
    return {"test_mechanic_lines": len(mechanic_lines(test)), "seen_in_train": 0}


def generate(pairs=480, seed=7, test_share=0.15):
    """(train_rows, test_rows). Test pairs come from the held-out family."""
    rng = random.Random(seed)
    n_test = int(round(pairs * test_share))
    train = [row for i in range(pairs - n_test) for row in make_pair(rng, i, "train")]
    test = [row for i in range(pairs - n_test, pairs)
            for row in make_pair(rng, i, "heldout")]
    return train, test


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=int, default=480)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--test-share", type=float, default=0.15)
    args = parser.parse_args()

    train, test = generate(args.pairs, args.seed, args.test_share)
    stats = verify(train, test)

    os.makedirs(OUT_DIR, exist_ok=True)
    for name, rows in (("minimal_pairs_train.csv", train), ("minimal_pairs_test.csv", test)):
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        kinds = {}
        for row in rows:
            kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
        print(f"wrote {name}: {len(rows)} rows - {kinds.get('full', 0) // 2} pairs, "
              f"{kinds.get('fragment', 0) // 2} fragment pairs, "
              f"{kinds.get('truncated', 0) // 2} truncated pairs, "
              f"{kinds.get('prefix', 0)} prefixes, {kinds.get('core', 0)} cores")
    print(f"held-out check: {stats['test_mechanic_lines']} distinct mechanic sentences "
          f"in test, {stats['seen_in_train']} of them in training")


if __name__ == "__main__":
    main()
