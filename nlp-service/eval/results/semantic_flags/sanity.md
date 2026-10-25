| pair | expected | e5-base | mesolitica 64M |
|---|---|---|---|
| "byr dlu baru blh tgk" vs "pay first before viewing" | should match | 0.759 | 0.796 |
| "rumah berkunci, tak boleh masuk tengok" vs "the unit is locked, no viewing" | should match | 0.857 | 0.614 |
| "I hantar keys by Poslaju" vs "kunci saya pos" | should match | 0.878 | 0.684 |
| "jangan bayar sebelum tengok" vs "bayar dulu sebelum tengok" | should NOT match | 0.969 | 0.891 |
| "boleh viewing dulu?" vs "bayar dulu baru viewing" | should NOT match | 0.899 | 0.538 |
| params_millions | | 278 | 48 |
| load_seconds | | 20.4 | 3.0 |
| real_scam_production_seconds | | 1.784 | 0.465 |
| real_legit_production_seconds | | 1.824 | 0.542 |
