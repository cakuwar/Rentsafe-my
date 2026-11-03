from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

SCAM_INDEX = 1  # ← change this to what you found in config.json (Step 1)
texts = {
    "SCAM": """Agent: Hi, the room at Bangsar South is still available. RM650 per month.
Tenant: Great, can I view it this weekend?
Agent: Sorry, the owner is working overseas now, so viewing is not possible.
Tenant: Oh, then how do I see the room?
Agent: I can send you photos. Many people are asking for this unit, so you need to decide fast.
Tenant: How do I book it?
Agent: Transfer RM1300 deposit to my personal Maybank account today to secure it.
Tenant: Can I pay after I see the room?
Agent: Cannot, if you don't pay today I will give it to the next person. The keys will be couriered to you after payment.""",

    "LEGIT": """Agent: Hi, the room at Bangsar South is still available. RM650 per month.
Tenant: Great, can I view it this weekend?
Agent: Sure, Saturday 11am is fine. I will meet you at the guardhouse.
Tenant: Okay, what documents do I need?
Agent: Just bring your IC. If you like the room, we can prepare the tenancy agreement.
Tenant: How does the deposit work?
Agent: Deposit is RM1300, paid to the company account after you sign the agreement.
Tenant: Can I see the agreement first?
Agent: Of course, I will email you a copy before Saturday so you can read it. My REN number is in my signature.""",
}


def p_scam_text(source, text):
    tok = AutoTokenizer.from_pretrained(source)
    model = AutoModelForSequenceClassification.from_pretrained(source)
    model.eval()
    inputs = tok(text, truncation=True, max_length=512, return_tensors="pt")
    with torch.no_grad():
        probs = torch.softmax(model(**inputs).logits, dim=-1)
    return probs[0, SCAM_INDEX].item()

print("Local:", p_scam_text("./nlp-service/models/xlm-roberta-scam-v3-run1", texts["SCAM"]))
print("Hub:  ", p_scam_text("cakuwar/rentsafe-xlmr-v3", texts["SCAM"]))