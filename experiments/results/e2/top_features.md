# E2 top 20 features per class

Positive weights push towards SCAM, negative towards LEGITIMATE. Features with equal weights may swap order between scikit-learn versions.

## Variant A (379 corpus rows), C = 10

| rank | towards SCAM | towards LEGITIMATE |
|---|---|---|
| 1 | `dulu` +1.44 | `renter okay` -0.95 |
| 2 | `view` +1.32 | `rumah` -0.90 |
| 3 | `kena` +1.02 | `check` -0.82 |
| 4 | `fee` +1.01 | `okay` -0.78 |
| 5 | `account` +0.97 | `thank you` -0.78 |
| 6 | `to` +0.96 | `thank` -0.78 |
| 7 | `balik` +0.89 | `house` -0.75 |
| 8 | `bayar` +0.87 | `owner rumah` -0.74 |
| 9 | `booking` +0.87 | `baik` -0.73 |
| 10 | `agreement` +0.86 | `bulan` -0.72 |
| 11 | `dia` +0.83 | `aircond` -0.72 |
| 12 | `it` +0.81 | `termasuk` -0.71 |
| 13 | `kalau` +0.81 | `ok saya` -0.70 |
| 14 | `aggrement` +0.81 | `masa` -0.69 |
| 15 | `proses` +0.80 | `furnished` -0.68 |
| 16 | `duit` +0.77 | `owner deposit` -0.67 |
| 17 | `lepas` +0.77 | `the deposit` -0.65 |
| 18 | `kena bayar` +0.75 | `dapur` -0.64 |
| 19 | `refund` +0.74 | `ok` -0.64 |
| 20 | `baru` +0.73 | `sampai` -0.63 |

## Variant B (run 1 data, 1,223 rows), C = 10

| rank | towards SCAM | towards LEGITIMATE |
|---|---|---|
| 1 | `dulu` +2.52 | `sign` -3.06 |
| 2 | `kena` +2.40 | `masa` -2.32 |
| 3 | `transfer` +2.02 | `masa sign` -2.10 |
| 4 | `to` +1.78 | `at` -1.92 |
| 5 | `baru` +1.73 | `signing` -1.68 |
| 6 | `then` +1.69 | `kat` -1.56 |
| 7 | `owner transfer` +1.53 | `ll meet` -1.56 |
| 8 | `you ll` +1.50 | `kat unit` -1.48 |
| 9 | `booking dulu` +1.49 | `meet` -1.47 |
| 10 | `account` +1.42 | `agreement` -1.40 |
| 11 | `kena bayar` +1.41 | `" sign"` (chars) -1.37 |
| 12 | `first` +1.34 | `" sig"` (chars) -1.37 |
| 13 | `owner kena` +1.34 | `jumpa` -1.36 |
| 14 | `refund` +1.32 | `meet you` -1.35 |
| 15 | `balik` +1.31 | `sign agreement` -1.30 |
| 16 | `it` +1.29 | `"sig"` (chars) -1.28 |
| 17 | `reserve` +1.26 | `"sign"` (chars) -1.28 |
| 18 | `owner saya` +1.24 | `"ign"` (chars) -1.28 |
| 19 | `bayar booking` +1.24 | `booking deposit` -1.27 |
| 20 | `tak` +1.22 | `no booking` -1.26 |
