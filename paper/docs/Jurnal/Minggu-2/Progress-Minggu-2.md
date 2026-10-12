# Progress Minggu 2 — State, Demand, dan Pembekuan Protokol

**Per 12 Oktober 2026:** Day 8 selesai; Day 9–14 belum dilaksanakan. Nomor *Day*
menunjuk tahap dalam [rencana teknis](../../../../teknis-lab/README.md), bukan
tanggal kalender. Jurnal ini membedakan hasil yang sudah diverifikasi dari pekerjaan
dan keputusan yang masih menunggu tahap berikutnya.

## Day 8 — Workload/state monitoring

**Status: selesai, 12 Oktober 2026.** [Monitor](../../../../src/monitor.py) merekonstruksi
state setiap klien dari prefix log event B0 yang dibekukan, tanpa mengubah dispatch,
pelatihan, agregasi, maupun pesan B0. Setiap snapshot memiliki unit, asal nilai,
waktu observasi, dan waktu nilai tersedia. Jumlah sampel diketahui saat start-up;
durasi training dan staleness baru diketahui setelah arrival; age dihitung sejak
accepted apply terakhir. Aturan nilai yang belum ada dan observasi tidak valid
dicatat dalam [skema Day 8](../../../../tasks/day8-state-schema.md).

Dua ulangan B0 Day 7 masing-masing menghasilkan **910 snapshot**: 10 klien pada
start-up dan setelah masing-masing dari 90 event. Setiap run mempunyai 30 accepted
updates dan 8.094.060 byte pesan aplikasi terserialisasi. Tidak ada durasi training
yang hilang atau tidak valid pada kedua run. RTT dan throughput **tetap null** dengan
status `unmeasured_process_pool_ipc`, karena B0 tidak merekam waktu transfer IPC.
Snapshot memakai batas waktu dan urutan event dalam log; waktu persis sebelum
pemilihan klien pada eksekusi live tidak direkam.

**Bukti:** [skema](../../../../tasks/day8-state-schema.md),
[snapshot dan manifest run A](../../../../results/processed/day8_monitor_a/manifest.json),
[run B](../../../../results/processed/day8_monitor_b/manifest.json), serta
[gate receipt](../../../../results/processed/day8_state_monitoring.json).
Seluruh **184 tes lulus**, termasuk uji konsistensi waktu, ketiadaan informasi dari
event masa depan, dan regresi hasil model/byte B0 pada trace yang sama. Verifier
kedua bundle dan manifest pembekuan fondasi Minggu 1 lulus. Langkah berikutnya:
kalibrasi distribusi state tanpa memakai skor official test.

## Day 9 — Calibration runs

**Status: belum dimulai.** Snapshot Day 8 sudah tersedia sebagai input, tetapi
belum ada statistik distribusi atau parameter normalisasi yang dibekukan. Tahap
ini harus mencatat min, max, median, p05/p25/p75/p95, dan sebaran untuk tiap fitur
yang dapat diamati, beserta satuan, sumber, rumus normalisasi/clipping, perilaku
nilai null/out-of-range, dan hash artefak. RTT/throughput belum memiliki pengukuran
di B0 dan tidak boleh diisi dengan angka turunan yang keliru.

**Bukti yang ditunggu:** artefak kalibrasi, ringkasan distribusi, dan tes transform
deterministik tanpa pemilihan parameter dari official-test score. Gate Day 9 belum
lulus; output ini menjadi input estimator Day 10.

## Day 10 — Demand estimator

**Status: belum dimulai.** Belum ada implementasi estimator atau nilai `d_part`
dan `d_budget` yang terverifikasi. Setelah kalibrasi Day 9, estimator perlu
memetakan state yang tersedia saat observasi ke dua skor terpisah, dengan formula,
arah kontribusi fitur, clipping, dan jejak state → demand yang dapat direplay.
Weights, threshold, dan action mapping masih keputusan pilot, belum dibekukan.

**Bukti yang ditunggu:** dokumen formula, keluaran deterministik dalam domain yang
ditetapkan, uji perturbasi fitur, dan tes bahwa label masa depan maupun metrik
official test tidak masuk ke input. Gate Day 10 belum lulus.

## Day 11 — Policy B1 dan B2

**Status: belum dimulai.** Definisi pembanding tetap: B0 memakai partisipasi
seragam dan budget 100%; B1 hanya mengubah partisipasi, sedangkan B2 hanya
mengubah budget 25/50/100%. Operator budget sudah diuji pada Day 6, tetapi
integrasi B1/B2 dalam run live belum ada.

**Bukti yang ditunggu:** snapshot konfigurasi B1/B2, log smoke run, serta laporan
selisih policy yang membuktikan B1 selalu memakai budget 100%, B2 tetap memilih
partisipasi seragam, dan model, local training, agregasi, partisi, concurrency,
serta profil pembanding tetap sama. Gate isolasi policy belum lulus.

## Day 12 — Policy B3 dan fairness guardrail

**Status: belum dimulai.** B3 akan memakai kedua aktuator—partisipasi dan budget—
dengan aturan yang mencegah klien tidak mendapat kesempatan kontribusi. Nilai
maximum inactivity window atau fairness floor masih harus diputuskan melalui pilot;
belum ada klaim bahwa starvation sudah dicegah.

**Bukti yang ditunggu:** konfigurasi dan implementasi B3, log alasan forced
participation, ringkasan kontribusi per klien, serta fixture yang membuktikan
guardrail, validitas action pada state ekstrem, dan local compute tetap. Gate
fairness belum lulus.

## Day 13 — Pilot B0–B3

**Status: belum dimulai.** Empat policy belum dijalankan bersama pada satu seed,
satu partisi, dan satu profil jaringan. Pilot ini diperlukan untuk memeriksa
lifecycle, demand → action mapping, staleness, byte accounting, fairness override,
dan kelengkapan log sebelum keputusan utama dibekukan. Dua replay B0 Day 7 dan
monitoring Day 8 bukan pengganti pilot B0–B3.

**Bukti yang ditunggu:** empat direktori run, log dan kurva validation, policy
diff, rekonsiliasi byte/payload, serta ledger issue dengan penyelesaian atau alasan
kegagalan yang jelas. Gate integrasi pilot belum lulus; hasil pilot tidak boleh
dipilih berdasarkan official-test score.

## Day 14 — Protocol freeze

**Status: belum dimulai.** Manifest pembekuan Minggu 1 hanya mencakup fondasi
CPU B0. Formula/weights/threshold demand, aturan fairness, grid action,
concurrency, profil RTT/bandwidth, interval evaluasi, target Macro-F1, stopping
rules, dan rencana analisis untuk main run masih menunggu kalibrasi dan pilot.

**Bukti yang ditunggu:** manifest protokol immutable dengan hash konfigurasi,
kalibrasi, partisi, serializer, dan policy; kriteria praktis dan target yang
ditetapkan sebelum analisis hasil utama; skema event yang disetujui; laporan
policy diff dan replay pilot; serta keputusan freeze yang tercatat. Gate Day 14
belum lulus. Main runs dimulai hanya setelah demand mapping, fairness, isolasi
policy, reproducibility, dan pembekuan protokol terverifikasi.
