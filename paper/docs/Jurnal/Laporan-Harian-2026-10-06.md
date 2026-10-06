# Laporan Harian DSIC-2907 — 6 Oktober 2026

**Lingkup:** verifikasi prasyarat Day 1, penyelesaian Day 2, dan implementasi serta pengujian pilot Day 3 sesuai bagian 13 pada panduan kepemilikan TA.

**Status akhir:** Day 1–3 telah selesai sampai tahap pilot B0. Day 4 menjadi pekerjaan berikutnya. Istilah *Day* mengacu pada paket pekerjaan dalam rencana penelitian, bukan jumlah hari kalender yang dihabiskan.

## 1. Ringkasan capaian

| Pekerjaan | Hasil hari ini | Bukti utama |
|---|---|---|
| Verifikasi fondasi Day 1 | Pipeline dan split tersimpan berhasil dimuat; delapan fingerprint artefak sesuai | Manifest dataset/preprocessing dan hasil centralized yang sudah ada |
| Day 2 — partition non-IID | Tiga partition deterministik, masing-masing sepuluh client, alpha 0.5 | [Artefak dan verifikasi partition](../../../data/partitions/README.md) |
| Day 3 — asynchronous B0 | Pilot seed 42 selesai dengan 30 accepted updates dan concurrency 3 | [Ringkasan pilot](../../../results/processed/b0_day3_seed42.json) |
| Reproduksibilitas | Partition/CSV dapat direproduksi; replay B0 menghasilkan bobot akhir identik | [Hasil replay B0](../../../results/processed/b0_day3_seed42_replay.json) |
| Pengujian | Suite akhir 93 tes lulus; lint, format, dan build berhasil | [Catatan verifikasi Day 3](Day-3-B0-Asynchronous-Training.md#commands-and-verification) |
| Dokumentasi | Status, prosedur, hasil, batas pengukuran, dan langkah berikutnya diperbarui | README utama, rencana teknis, jurnal, dan panduan TA Markdown/PDF |

## 2. Verifikasi prasyarat Day 1

Sebelum membangun partition, artefak baseline terpusat yang sudah selesai diperiksa kembali. Pipeline preprocessing dapat dimuat dan memiliki pembagian data berikut:

- **140.272 baris train-fit** untuk pelatihan dan pembagian client;
- **35.069 baris validation** yang tetap terpisah dari pelatihan client;
- **192 fitur** hasil preprocessing yang urutannya dipertahankan.

Delapan referensi artefak cocok dengan SHA256 tersimpan: checkpoint, konfigurasi run, manifest dataset, manifest preprocessing, konfigurasi preprocessing, daftar fitur, pipeline, dan indeks split. Model centralized tidak dilatih ulang dan evaluasi official test tidak diulang. Pekerjaan hari ini memakai fondasi Day 1 yang sudah tersedia.

## 3. Day 2 — ten-client Dirichlet partition

Placeholder pada `src/partition.py` diganti dengan implementasi pembagian berdasarkan label Normal/Attack. Partition dibuat untuk seed **42, 123, dan 2026**, masing-masing dengan **10 client** dan **alpha 0.5**. Ketiganya tetap memakai split train-fit/validation Day 1 yang sama.

Setiap partition mencakup seluruh 140.272 baris train-fit tepat satu kali: 44.800 Normal dan 95.472 Attack. Tidak ada overlap antar-client atau baris validation di dalam partition. Official test tidak dibuka.

| Seed partition | Jumlah client | Total baris | Client terkecil | Client terbesar |
|---|---:|---:|---:|---:|
| 42 | 10 | 140.272 | 2.864 | 60.183 |
| 123 | 10 | 140.272 | 2.008 | 32.829 |
| 2026 | 10 | 140.272 | 959 | 56.959 |

Untuk setiap seed disimpan tiga berkas di `data/partitions/`: JSON alokasi indeks, CSV distribusi kelas, dan manifest berisi parameter serta fingerprint sumber/hasil. Indeks yang disimpan adalah posisi baris berbasis nol pada CSV training resmi.

Pengulangan menghasilkan byte partition dan CSV yang identik. Manifest juga identik ketika lokasi output sama; pengulangan di direktori berbeda hanya mengubah referensi lokasi output. Pembuatan artefak menolak penimpaan file yang sudah ada. Tidak ada client kosong pada tiga partition yang dihasilkan.

## 4. Day 3 — pilot B0 asynchronous training

Implementasi client dan server dilengkapi, lalu launcher `src/b0.py` ditambahkan. Client berjalan pada proses CPU terpisah. Setiap client menerima model global beserta versinya, melakukan pelatihan lokal, lalu mengirim seluruh delta model. Server menerapkan update menurut urutan penyelesaian tanpa menunggu seluruh client menyelesaikan satu putaran.

Komponen yang dipakai ulang adalah trainer, arsitektur MLP, preprocessing, pemeriksaan hash, dan metrik dari pekerjaan sebelumnya. Trainer mendapat opsi untuk memulai dari bobot hasil download. Tidak ada dependency baru yang ditambahkan.

### Konfigurasi pilot yang dijalankan

| Parameter | Nilai |
|---|---|
| Policy | B0 Async-Uniform |
| Seed / jumlah client | 42 / 10 |
| Concurrency | Maksimal 3 proses client aktif |
| Participation | Pemilihan seragam dari client yang sedang idle |
| Update budget | 100% pada seluruh update |
| Model | MLP 192 → 128 → 64 → 1, dropout 0.2, fp32 |
| Pelatihan lokal | Adam 0.001, batch 64, satu epoch per dispatch |
| CPU threads | Satu per proses |
| Aggregation | `global += (client_samples / 140272) * delta` |
| Server learning rate / fixed staleness multiplier | 1.0 / 1.0 |
| Batas pilot | 30 accepted updates |
| Evaluasi validation | Versi 0, 10, 20, dan 30 |
| Checkpoint | Initial, versi 25, dan final versi 30 |

Parameter tersebut tercatat dalam [konfigurasi pilot](../../../configs/day3_b0.yaml) dan snapshot run. Statusnya adalah pilihan pilot; pembekuan protokol eksperimen utama tetap direncanakan pada Day 14.

### Hasil dan bukti asynchronous

Pilot menyelesaikan **30 accepted updates**, mencapai **server version 30**, dan menghasilkan **90 event** download/arrival/apply. Seluruh sepuluh client berkontribusi setidaknya sekali.

`client_0` menerima model pada version 0 dan baru diterapkan pada version 14. Artinya, server telah menerapkan 13 update lain sebelum client tersebut selesai. Tes terkontrol juga membuktikan bahwa client cepat dapat diterapkan dan dikirim bekerja kembali sementara client lambat masih tertahan. Staleness maksimum yang tercatat pada pilot adalah 13.

| Server version | Validation Macro-F1 |
|---:|---:|
| 0 | 0.242906 |
| 10 | 0.736445 |
| 20 | 0.920266 |
| 30 | **0.924870** |

Attack Recall validation akhir adalah **0.994135**. Angka ini berasal dari global validation, bukan official test. Official test tidak dievaluasi dalam pekerjaan hari ini.

Replay memverifikasi hash pesan, model yang didownload, transisi versi, bobot aggregation, dan total panjang payload. Bobot model final hasil replay identik dengan checkpoint pilot.

### Artefak pilot

- [`results/raw/b0_day3_seed42/`](../../../results/raw/b0_day3_seed42/): konfigurasi, initial/final/periodic checkpoints, pesan model dan delta, event log, version history, validation curve, serta manifest.
- [`results/processed/b0_day3_seed42.json`](../../../results/processed/b0_day3_seed42.json): ringkasan pilot beserta referensi hash artefak.
- [`results/processed/b0_day3_seed42_replay.json`](../../../results/processed/b0_day3_seed42_replay.json): bukti replay berhasil.
- [Jurnal teknis Day 3](Day-3-B0-Asynchronous-Training.md): rincian keputusan, perintah, hasil, dan batas reproduksibilitas.

## 5. Pengujian dan pemeriksaan yang telah dijalankan

| Pemeriksaan | Hasil |
|---|---|
| Suite setelah Day 2 | 75 tes lulus |
| Suite akhir setelah Day 3 | **93 tes lulus** |
| `python -m ruff check src tests` | Lulus |
| Ruff format check untuk file Day 3 | Lulus |
| `python -m build --no-isolation` | Wheel dan source distribution berhasil dibuat |
| `python -m src.partition` | Tiga partition utama berhasil disimpan |
| `python -m src.b0 train --config configs/day3_b0.yaml` | Pilot selesai, 30 update diterima |
| `python -m src.b0 replay --run-dir results/raw/b0_day3_seed42` | Final model dan total panjang payload cocok |
| Pandoc/XeLaTeX untuk panduan TA | PDF berhasil dibangun; teks status dan tampilan tabel Week 1 diperiksa |
| `git diff --check` | Lulus |

Perintah Python memakai environment yang sudah tersedia di `/home/fadil/TA/Code/demand-aware-async-fl-nids/.venv/`. Rincian perintah lengkap tersimpan pada jurnal Day 3. Error lint lama berupa variabel `staleness` yang tidak digunakan selesai ketika nilai tersebut digunakan dalam receipt apply server.

Codebase index gagal saat bootstrap; implementasi dilanjutkan berdasarkan pemeriksaan file sumber secara langsung. Kegagalan alat indeks tersebut tidak menghalangi pengujian dan eksekusi pilot.

## 6. Peta file yang dikerjakan hari ini

| Kelompok | File/lokasi | Perubahan |
|---|---|---|
| Partition | `src/partition.py`, `tests/test_partition.py` | Implementasi, CLI, validasi, dan pengujian determinisme/isolasi data |
| Artefak Day 2 | `data/partitions/` | Sembilan artefak untuk tiga seed dan dokumentasi verifikasi |
| Backbone B0 | `src/client.py`, `src/async_server.py`, `src/b0.py` | Local training, full delta, immediate apply, dispatch asynchronous, logging, dan replay |
| Trainer bersama | `src/centralized.py` | Opsi initial state dan pengaturan keluaran log epoch untuk reuse pada client |
| Konfigurasi | `configs/day3_b0.yaml` | Parameter serta lokasi output pilot |
| Tes B0 | `tests/test_async_apply.py`, `tests/test_client.py`, `tests/test_b0.py` | Pengujian aggregation, determinisme client, no-barrier, kegagalan, dan replay |
| Hasil B0 | `results/raw/b0_day3_seed42/`, `results/processed/b0_day3_seed42*.json` | Bukti run dan replay |
| Dokumentasi | `README.md`, `teknis-lab/README.md`, `paper/TA-Ownership-Guide.md`, `paper/TA-Ownership-Guide.pdf` | Status Day 2/3 dan pekerjaan berikutnya |
| Jurnal | `paper/docs/Jurnal/Day-3-B0-Asynchronous-Training.md`, laporan harian ini | Catatan teknis tahap dan rangkuman aktivitas tanggal 6 Oktober |

Perubahan lain yang sudah ada di working tree, termasuk `paper/manuscript.md`, tidak dicatat sebagai hasil implementasi hari ini. Artefak raw mengikuti aturan Git ignore yang sudah ada dan perlu disimpan bersama dataset/preprocessing untuk reproduksi.

## 7. Batas hasil dan tindak lanjut

Hasil hari ini membuktikan bahwa partition dan backbone B0 pilot berfungsi. Perbandingan B0–B3 dan manfaat demand-aware participation/update budgeting belum diuji.

Total panjang payload terserialisasi yang tercatat adalah **4.046.070 byte upload** dan **4.047.990 byte download**. Angka ini belum mencakup envelope IPC, bootstrap data, atau overhead jaringan, sehingga belum digunakan sebagai klaim efisiensi komunikasi. Pelengkapan accounting dan pemisahan timing berada pada Day 5.

Urutan selesai client pada live run dipengaruhi penjadwalan OS. Training lokal deterministik untuk input, bobot, konfigurasi, dan seed yang sama; replay model menggunakan urutan kedatangan yang tersimpan. Keduanya telah diuji dengan cakupan tersebut.

Pekerjaan berikutnya adalah **Day 4 — verifikasi versioning dan staleness dengan kondisi fast/slow yang terkontrol**, dilanjutkan Day 5 byte accounting, Day 6 budget 25/50/100%, dan Day 7 backbone freeze.

Laporan ini merangkum pemeriksaan dan run yang telah dilakukan pada sesi implementasi hari ini. Penyusunan laporan hanya membaca artefak yang tersimpan dan memeriksa dokumentasi; tidak menjalankan ulang training atau evaluasi official test.
