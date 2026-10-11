# Progres Minggu 1 — Fondasi B0 Asinkron

**Status:** Day 1–7 selesai sampai pembekuan fondasi pilot CPU B0 pada 11 Oktober 2026. Istilah *Day* mengikuti tahap rencana kerja, bukan hari kalender. Protokol eksperimen utama masih dijadwalkan untuk Day 14.

## Capaian

| Tahap | Hasil |
| --- | --- |
| Day 1 — Data dan baseline | Pasangan CSV resmi UNSW-NB15 dicatat hash dan skemanya. Dari 175.341 baris training, 140.272 dipakai untuk train-fit dan 35.069 untuk validation. Preprocessing hanya di-*fit* pada train-fit; 42 fitur sumber menjadi 192 fitur model. MLP terpusat dilatih sebagai pemeriksaan alur. |
| Day 2 — Partisi klien | Tiga partisi non-IID dengan Dirichlet `alpha=0.5`, masing-masing 10 klien untuk seed 42, 123, dan 2026. Tiap partisi memuat seluruh 140.272 baris train-fit tepat sekali, tanpa validation atau test. |
| Day 3 — B0 asinkron | Pilot seed 42 menjalankan 30 update dengan maksimum tiga klien aktif, pemilihan seragam di antara klien yang sedang idle, dan budget update 100%. Server menerapkan update segera setelah tiba. Validation Macro-F1 akhir 0,924870; replay menghasilkan bobot akhir yang identik. |
| Day 4 — Versi dan staleness | Staleness dihitung dari versi server saat kedatangan dikurangi versi model yang diunduh klien. Uji klien cepat/lambat menghasilkan staleness 0, 0, dan 2. Update yang ditolak tidak menaikkan versi. Replay Day 3 memverifikasi 30 transisi dengan staleness 0–13. |
| Day 5 — Hitung byte | Pilot B0 baru mencatat panjang pesan aplikasi terserialisasi: 4.047.990 byte download dan 4.046.070 byte upload, total 8.094.060 byte untuk 30 update. Replay mencocokkan payload, akumulasi byte, dan model akhir. |
| Day 6 — Budget update | Operator magnitude top-k 25/50/100% diuji pada **satu delta Day 5 yang sama**, tanpa melatih ulang model. Ketiga pesan berhasil didekode dan diterapkan. B0 saat ini masih memakai budget 100%. |
| Day 7 — Bekukan fondasi | Dua ulangan B0 dengan input, konfigurasi, dan bobot awal yang sama menerima 30 update masing-masing. Keduanya mencatat 8.094.060 byte dan lulus replay. Manifest menyimpan konfigurasi, hash komponen, skema event, serta keputusan yang belum dibekukan. |

## Angka penting

Baseline terpusat Day 1 mencapai Macro-F1 **0,935908** pada validation dan **0,834634** pada test resmi. Test resmi dievaluasi **sekali** setelah checkpoint disimpan; Day 2–7 tidak mengevaluasinya lagi. Pada test, 11.993 dari 37.000 sampel Normal salah ditandai sebagai Attack. Baseline ini hanya pemeriksaan awal, bukan hasil perbandingan FL.

Pada pilot B0 Day 3, Macro-F1 validation di versi 0/10/20/30 adalah **0,242906 / 0,736445 / 0,920266 / 0,924870**. Seorang klien mengunduh versi 0 dan baru diterapkan pada versi 14; server telah menerima 13 update lain tanpa menunggunya. Bobot akhir ulangan Day 7 berbeda karena urutan kedatangan berbeda, tetapi tiap ulangan cocok dengan replay-nya sendiri.

| Budget pada satu delta Day 6 | Upload | Download | Total | Selisih dari 100% |
| ---: | ---: | ---: | ---: | ---: |
| 25% | 70.463 byte | 134.933 byte | 205.396 byte | Hemat 64.406 byte (23,872%) |
| 50% | 136.511 byte | 134.933 byte | 271.444 byte | Lebih besar 1.642 byte (0,609%) |
| 100% | 134.869 byte | 134.933 byte | 269.802 byte | Acuan |

Budget 50% lebih besar karena indeks dan metadata sparse ikut dikirim. Angka ini mengukur **pesan aplikasi terserialisasi**, termasuk header dan metadata, bukan lalu lintas jaringan fisik. Envelope IPC dan waktu transfer belum diukur. Satu delta tetap belum cukup untuk menyimpulkan penghematan pada pelatihan langsung atau pengaruh budget terhadap kualitas model.

## Bukti dan batas lanjutan

Artefak utama: [manifest data](../../../../data/manifests/dataset.json), [manifest preprocessing](../../../../data/manifests/preprocessing.json), [partisi klien](../../../../data/partitions/README.md), [hasil baseline](../../../../results/processed/centralized_seed42_test.json), [ringkasan B0 Day 3](../../../../results/processed/b0_day3_seed42.json), [hasil byte Day 5](../../../../results/processed/b0_day5_seed42.json), [probe budget Day 6](../../../../results/processed/b0_day6_budget_probe_seed42.json), dan [manifest pembekuan Day 7](../../../../results/processed/week1_backbone_freeze.json). Log, pesan, dan checkpoint mentah berada di `results/raw/` dan tidak seluruhnya tersedia dalam Git.

Verifikasi terakhir pada Day 7: **136 tes lulus**, Ruff, build paket, replay kedua ulangan, dan pemeriksa manifest lulus. Pembekuan ini berlaku untuk fondasi **pilot CPU B0**. Batas sumber daya, profil jaringan, aturan demand dan fairness, target Macro-F1, aturan berhenti, serta rencana analisis untuk eksperimen utama masih menunggu pilot atau keputusan Day 14. Belum ada perbandingan B0–B3 atau klaim efisiensi komunikasi jaringan.
