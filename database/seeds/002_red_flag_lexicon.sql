-- Seed: bilingual red-flag lexicon for Layer 1 (mirrors app/layer1/red_flags.py).
-- Keeping these in the DB lets you tune weights without redeploying the NLP service.
INSERT INTO red_flag_lexicon (category, phrase, language, weight) VALUES
  ('upfront_payment_demand', 'bayar deposit dulu',      'ms',    1.0),
  ('upfront_payment_demand', 'transfer dulu',            'ms',    1.0),
  ('upfront_payment_demand', 'pay first',                'en',    1.0),
  ('urgency_pressure',       'cepat sebelum orang lain', 'ms',    0.8),
  ('urgency_pressure',       'today only',               'en',    0.8),
  ('no_viewing_allowed',     'tidak boleh tengok',       'ms',    1.0),
  ('no_viewing_allowed',     'owner overseas',           'en',    1.0),
  ('offplatform_contact',    'whatsapp sahaja',          'ms',    0.6),
  ('too_good_to_be_true',    'murah gila',               'ms',    0.7),
  ('courier_key_scam',       'pos kunci',                'ms',    1.0)
ON CONFLICT (category, phrase) DO NOTHING;
