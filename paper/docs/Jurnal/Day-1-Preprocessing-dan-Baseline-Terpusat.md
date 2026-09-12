# Jurnal Day 1 — Preprocessing UNSW-NB15 dan Baseline MLP Terpusat

**Tanggal penyusunan:** 12 September 2026  
**Status:** Implementasi dan evaluasi Day 1 selesai.  
**Lokasi proyek:** root repositori DSIC-2907

## 1. Tujuan pekerjaan

Day 1 membangun fondasi eksperimen untuk penelitian:

> Demand-Aware Adaptive Participation and Update Budgeting for Communication-Efficient Asynchronous Federated Network Intrusion Detection under Non-IID Data.

Target hari pertama adalah memastikan bahwa data dapat diproses dengan benar, model sederhana dapat dilatih, dan hasilnya dapat ditelusuri kembali ke data serta konfigurasi yang digunakan. Model terpusat ini merupakan **sanity baseline**, yaitu pemeriksaan awal bahwa alur eksperimen berfungsi secara masuk akal. Model ini bukan kontribusi utama penelitian dan belum menjadi pembanding final bagi eksperimen Federated Learning.

Lingkup yang selesai meliputi identifikasi dataset, preprocessing, pelatihan MLP terpusat, evaluasi, pengujian otomatis, dan dokumentasi. **Belum ada** pembagian klien FL, eksekusi asinkron, estimasi demand, scheduling, kompresi, maupun emulasi jaringan.

## 2. Dataset yang digunakan dan identitasnya

Dataset yang digunakan adalah **UNSW-NB15 varian pasangan CSV training/testing resmi** yang sudah tersedia di workspace:

```text
data/raw/UNSW-NB15/OneDrive_3_9-7-2026/
└── CSV Files/Training and Testing Sets/
    ├── UNSW_NB15_training-set.csv
    └── UNSW_NB15_testing-set.csv
```

Empat CSV dataset lengkap (`UNSW-NB15_1.csv` sampai `UNSW-NB15_4.csv`) tidak digunakan untuk membentuk ulang pembagian data.

| Pembagian resmi | Jumlah baris | Normal (0) | Attack (1) | Proporsi Attack |
| --- | ---: | ---: | ---: | ---: |
| Training | 175.341 | 56.000 | 119.341 | 68,06% |
| Test | 82.332 | 37.000 | 45.332 | 55,06% |

Sebelum preprocessing, pasangan CSV diaudit dan dicatat dalam `data/manifests/dataset.json`. Manifest adalah berkas metadata yang menjelaskan **data mana yang digunakan**, bukan salinan isi dataset. Isinya mencakup nama/varian dataset, nama dan lokasi file, urutan kolom, tipe data hasil pemeriksaan, aturan parsing, target, pemetaan label, jumlah kelas, serta SHA256 kedua CSV.

SHA256 berfungsi sebagai sidik jari isi file. Contohnya, jika CSV diganti atau diedit setelah identitasnya dibekukan, hash yang dihitung berikutnya akan berbeda dan proses harus menolak file tersebut. Hash ini mengidentifikasi file lokal yang dipakai; bukan bukti independen bahwa file telah diverifikasi langsung oleh penerbit dataset.

Pemeriksaan juga menemukan **UTF-8 BOM** pada header. Pembacaan menggunakan `utf-8-sig` agar kolom pertama dikenali sebagai `id`, bukan nama dengan karakter tersembunyi. Skema yang tidak sesuai—misalnya kolom hilang, tambahan, duplikat, atau urutannya berubah—ditolak, bukan ditebak maknanya.

## 3. Pemisahan target dan fitur

Tugas dibatasi menjadi klasifikasi biner:

```text
y = label
0 = Normal
1 = Attack
```

`label` digunakan langsung sebagai target. Target **tidak diturunkan dari `attack_cat`**.

| Kolom yang dikeluarkan dari input | Alasan |
| --- | --- |
| `id` | Pengenal baris, bukan fitur perilaku jaringan yang ingin dipelajari |
| `attack_cat` | Memuat informasi kategori serangan; berpotensi membocorkan jawaban |
| `label` | Jawaban yang harus diprediksi, bukan informasi masukan |

**Contoh ilustratif:** sebuah baris memiliki `proto=udp`, `attack_cat=Generic`, dan `label=1`. Model boleh mempelajari protokol dan fitur trafik lainnya, tetapi tidak boleh melihat `Generic` atau `1` sebagai input. Jika jawaban ikut dimasukkan ke fitur, metrik bisa tampak sangat baik tanpa menunjukkan kemampuan deteksi yang sebenarnya.

Dari 45 kolom sumber, tersisa **42 fitur**: 39 numerik dan tiga kategorikal (`proto`, `service`, `state`). Nilai label selain 0/1, nilai numerik tidak valid/tidak terhingga, serta missing value ditolak. Tidak ada imputer yang dilatih pada Day 1.

## 4. Pembagian validation dilakukan sebelum preprocessing fit

Training resmi dibagi secara **stratified** dengan seed 42 dan porsi validation 20%. Stratified berarti proporsi Normal/Attack dijaga mendekati proporsi training resmi.

| Subset dari training resmi | Jumlah baris | Normal | Attack |
| --- | ---: | ---: | ---: |
| Train-fit (80%) | 140.272 | 44.800 | 95.472 |
| Validation (20%) | 35.069 | 11.200 | 23.869 |

Train-fit adalah bagian yang benar-benar dipakai untuk mempelajari preprocessing dan bobot model. Validation dipakai untuk pemeriksaan hasil model. Keduanya tidak saling tumpang tindih, dan jika digabung mencakup seluruh training resmi.

Urutan yang diterapkan:

```text
Training resmi
    ├── Train-fit ──> fit scaler + encoder ──> latih MLP
    └── Validation ─> transform saja ────────> evaluasi model akhir

Test resmi ────────> transform saja ────────> satu evaluasi final terpisah
```

**Mengapa urutan ini penting?** Misalnya fitur numerik pada train-fit adalah `[10, 20, 30]`, sedangkan validation berisi `[1000]`. Rata-rata scaler harus dihitung sebagai `20`, bukan `265` dari gabungan keduanya. Memakai validation untuk menghitung statistik berarti informasi held-out sudah ikut memengaruhi proses belajar, walaupun labelnya tidak digunakan.

Indeks pembagian disimpan sebagai posisi baris asli berbasis nol dalam `split_indices.npz`. Dengan demikian, pembagian dapat diperiksa dan digunakan kembali tanpa mengandalkan tebakan dari urutan data yang telah ditransformasi.

## 5. Preprocessing: scaling, encoding, dan penyimpanan

Implementasi menggunakan **sklearn ColumnTransformer** untuk memisahkan perlakuan numerik dan kategorikal.

- **Numerik:** StandardScaler mempelajari rata-rata dan simpangan baku dari train-fit saja. Secara sederhana, transformasinya adalah `z = (x − rata-rata_train_fit) / simpangan_baku_train_fit`.
- **Kategorikal:** OneHotEncoder mempelajari daftar kategori dari train-fit saja, dengan `handle_unknown="ignore"`.
- **Validation/test:** hanya menjalankan `transform`; tidak menghitung ulang statistik dan tidak memanggil `fit`.

**Contoh encoding ilustratif:** jika kategori `proto` yang dipelajari adalah `[tcp, udp]`, representasinya adalah `tcp → [1, 0]` dan `udp → [0, 1]`. Apabila validation/test berisi kategori baru, indikator untuk kolom tersebut menjadi `[0, 0]`. Jumlah fitur tidak berubah dan kategori baru tidak dimasukkan diam-diam ke encoder.

Pada data aktual, 42 fitur sumber menjadi **192 fitur input model** setelah encoding. Urutan nama fitur hasil transformasi disimpan agar model selalu menerima kolom dalam urutan yang sama.

Array hasil transformasi **tidak disimpan sebagai artefak utama**. Artefak utamanya adalah pipeline yang sudah fit, indeks pembagian, nama fitur, konfigurasi, dan manifest. Matriks aktual tetap sparse di memori; hanya minibatch yang dikonversi menjadi dense untuk PyTorch. Ini menghindari penyimpanan banyak angka nol yang tidak diperlukan.

## 6. Model MLP dan proses pelatihan

Arsitektur yang digunakan:

```text
192 input → Linear(128) → ReLU → Dropout(0,1)
          → Linear(64) → ReLU → Linear(1)
```

| Konfigurasi | Nilai |
| --- | --- |
| Seed | 42 |
| Epoch | 10 |
| Batch size | 512 |
| Optimizer | Adam |
| Learning rate | 0,001 |
| Dropout | 0,1 |
| Perangkat | CPU, satu thread |
| Parameter yang dilatih | 33.025 |
| Loss | BCEWithLogitsLoss |

Satu epoch berarti satu putaran atas seluruh data train-fit. Minibatch berisi paling banyak 512 sampel. Dropout secara acak menonaktifkan sebagian aktivasi saat training; dropout tidak aktif saat evaluasi.

Output model berupa **logit**. Fungsi sigmoid mengubahnya menjadi skor probabilitas Attack untuk evaluasi. Angka ini tidak dikalibrasi sebagai estimasi probabilitas operasional pada Day 1.

Pelatihan sepuluh epoch selesai dengan durasi **5,60 detik untuk loop training saja**, bukan waktu keseluruhan audit, preprocessing, dan evaluasi. Rata-rata training loss turun dari **0,201183** pada epoch pertama menjadi **0,114063** pada epoch kesepuluh.

Checkpoint yang disimpan adalah **model pada epoch terakhir**. Tidak dilakukan pencarian hyperparameter, pemilihan checkpoint berdasarkan test, atau perubahan threshold berdasarkan hasil test. Final validation dicatat tanpa mengubah konfigurasi run ini.

## 7. Metrik dan hasil evaluasi

Kelas positif selalu **Attack = 1**. Keputusan kelas menggunakan threshold tetap:

```text
Skor Attack ≥ 0,5 → prediksi Attack
Skor Attack < 0,5 → prediksi Normal
```

Contoh: skor `0,70` menghasilkan Attack, sedangkan `0,30` menghasilkan Normal. Skor tepat `0,50` juga menghasilkan Attack.

| Metrik | Makna ringkas | Validation | Test resmi |
| --- | --- | ---: | ---: |
| **Macro-F1** | Rata-rata F1 Normal dan Attack, bobot kelas sama | 0,935908 | **0,834634** |
| **Attack Recall** | Bagian serangan aktual yang berhasil terdeteksi | 0,978885 | **0,981007** |
| **AUPRC / Average Precision** | Ringkasan precision–recall dari skor Attack | 0,995007 | **0,980808** |
| Accuracy | Proporsi seluruh prediksi yang benar | 0,945507 | 0,843876 |
| AUROC | Ukuran pemeringkatan skor antar kelas | 0,989537 | 0,973654 |
| Balanced Accuracy | Rata-rata recall Normal dan Attack | 0,926630 | 0,828436 |

Tiga metrik pertama adalah metrik utama. AUPRC diimplementasikan sebagai **Average Precision** melalui `sklearn.metrics.average_precision_score`, bukan integrasi trapezoidal kurva PR. Average Precision dan AUROC dihitung dari skor probabilitas, sedangkan metrik klasifikasi memakai keputusan pada threshold 0,5.

### Membaca confusion matrix

Confusion matrix test adalah `[[25007, 11993], [861, 44471]]`. Baris menunjukkan kelas sebenarnya dan kolom menunjukkan prediksi, dengan urutan `[Normal, Attack]`.

| Kelas sebenarnya | Prediksi Normal | Prediksi Attack |
| --- | ---: | ---: |
| Normal | 25.007 — TN, normal dikenali benar | 11.993 — FP, alarm palsu |
| Attack | 861 — FN, serangan terlewat | 44.471 — TP, serangan terdeteksi |

Contoh perhitungan:

```text
Attack Recall = TP / (TP + FN)
              = 44.471 / 45.332 ≈ 98,10%

False Positive Rate = FP / (FP + TN)
                    = 11.993 / 37.000 ≈ 32,41%

Accuracy = (TP + TN) / semua sampel
         = (44.471 + 25.007) / 82.332 ≈ 84,39%
```

False Positive Rate di atas merupakan perhitungan penjelas dari confusion matrix, bukan field metrik tambahan yang disimpan oleh program.

**Interpretasi:** model menangkap sebagian besar serangan, tetapi sekitar 32 dari setiap 100 sampel Normal pada test salah ditandai sebagai Attack. Artinya, recall tinggi tidak otomatis berarti model sudah layak dipakai sebagai NIDS operasional. Average Precision yang tinggi juga tidak menjamin sedikit alarm palsu pada satu threshold tertentu.

Macro-F1 validation lebih tinggi daripada test. Hal ini menunjukkan hasil validation tidak dapat langsung dianggap mewakili hasil test. Proporsi kelas keduanya memang berbeda, tetapi hasil ini saja **belum cukup untuk memastikan penyebab selisih**, misalnya pergeseran distribusi fitur atau overfitting. Tidak dilakukan perubahan model atau threshold untuk mengejar skor test yang lebih baik.

## 8. Isolasi test dan jejak asal artefak

Test resmi dibaca saat audit awal hanya untuk identitas/skema, validasi nilai, hash, dan jumlah data. Setelah itu, kode persiapan training, pelatihan, serta validation tidak membuka kembali CSV atau array test. Jumlah test dalam metadata training berasal dari manifest yang sudah dibekukan.

Pembukaan test berikutnya dilakukan melalui **satu perintah evaluasi final terpisah**, setelah checkpoint disimpan. Evaluasi memeriksa hash, memuat preprocessing yang telah fit, melakukan transformasi, dan menghitung metrik. Test tidak digunakan untuk memilih epoch, learning rate, arsitektur, preprocessing, threshold, maupun checkpoint.

Jejak asal hasil, atau **provenance**, tersusun sebagai berikut:

```text
JSON hasil evaluasi
  → SHA256 checkpoint model
  → SHA256 manifest preprocessing
  → SHA256 manifest dataset
  → SHA256 CSV training dan test
```

Manifest preprocessing juga menghubungkan hash pipeline, indeks pembagian, daftar fitur, dan konfigurasi. Contoh manfaatnya: jika checkpoint dari eksperimen lain tertukar, pemeriksaan hash akan menolak ketidakcocokan sebelum evaluasi diteruskan.

Artefak penting, relatif terhadap direktori proyek:

| Artefak | Isi/fungsi |
| --- | --- |
| `data/manifests/dataset.json` | Identitas dan skema dataset, label, jumlah data, hash sumber |
| `data/manifests/preprocessing.json` | Lingkup fit, pembagian data, versi paket, hash artefak |
| `data/processed/pipeline.joblib` | ColumnTransformer yang sudah fit pada train-fit |
| `data/processed/split_indices.npz` | Posisi baris train-fit dan validation |
| `data/processed/feature_names.json` | Urutan 192 fitur hasil transformasi |
| `data/processed/preprocessing_config.json` | Salinan konfigurasi preprocessing |
| `results/raw/centralized_seed42/configuration.json` | Salinan konfigurasi model dan eksperimen |
| `results/raw/centralized_seed42/model.pt` | Bobot akhir dan metadata run |
| `results/raw/centralized_seed42/training.json` | Hash checkpoint, loss, durasi, dan final validation |
| `results/processed/centralized_seed42_test.json` | Semua metrik test dan provenance |

Dataset mentah, environment lokal, dan artefak biner tidak disertakan dalam publikasi GitHub. Manifest serta hasil JSON yang kecil disertakan. Karena itu, clone repository tidak otomatis menyediakan dataset, pipeline biner, atau checkpoint lokal.

## 9. Reproducibility dan pengujian

Python, NumPy, dan PyTorch diberi seed. Pembagian data deterministik dan DataLoader menggunakan generator shuffle dengan seed tetap serta tanpa worker subprocess. Pengujian pada environment yang sama memastikan urutan minibatch dan bobot hasil training dapat diulang.

Versi utama yang tercatat dalam run: Python **3.14.4**, NumPy **2.5.3**, pandas **2.3.3**, scikit-learn **1.9.0**, dan PyTorch **2.14.0+cpu**. Daftar lengkap tersedia di JSON hasil. Reproducibility diharapkan dalam environment dan konfigurasi yang tercatat, bukan jaminan identik bit-per-bit pada semua versi atau perangkat.

**Hasil verifikasi implementasi: 46 tes lulus**, pemeriksaan lint/format Ruff lulus, serta build source distribution dan wheel berhasil. Cakupan pentingnya:

- Skema resmi dikenali, sedangkan skema ambigu dan label tidak valid ditolak.
- Hash serta jumlah data tercatat; perubahan sumber atau artefak terdeteksi.
- Split deterministik, tidak tumpang tindih, dan mendahului preprocessing fit.
- Statistik scaler/kategori encoder berasal hanya dari train-fit.
- Transform validation/test tidak melakukan refit; kategori baru aman; fitur konsisten.
- `label` menjadi target langsung; `id`, `attack_cat`, dan `label` tidak masuk input.
- Metrik cocok dengan contoh terkontrol, termasuk threshold dan urutan confusion matrix.
- Penjagaan akses file membuktikan perintah training tidak membuka test.
- Evaluasi memerlukan checkpoint, mencatat provenance, dan menolak overwrite hasil.

Tes menggunakan dataset sintetis, bukan membaca test resmi berulang kali. Contohnya, tes preprocessing menaruh angka ekstrem dan kategori khusus hanya pada validation untuk memastikan keduanya tidak memengaruhi scaler atau encoder.

## 10. Cara melihat hasil dan mengulang alur

Untuk membaca hasil yang sudah ada, tanpa menjalankan ulang evaluasi:

```bash
cd /home/fadil/DSIC-2907/DSIC-2907
.venv/bin/python -m json.tool results/processed/centralized_seed42_test.json
```

Alur eksekusi yang digunakan adalah **install dependency → freeze identitas dataset → prepare → train/validation → evaluate**. Setelah instalasi dan pembekuan identitas selesai, perintah utamanya:

```bash
.venv/bin/python -m src.preprocess prepare --config configs/day1_experiments.yaml
.venv/bin/python -m src.centralized train \
  --config configs/day1_experiments.yaml --model-config configs/day1_model.yaml
.venv/bin/python -m src.centralized evaluate \
  --checkpoint results/raw/centralized_seed42/model.pt \
  --output results/processed/centralized_seed42_test.json
```

Perintah tersebut adalah catatan reproduksi, **bukan instruksi untuk mengevaluasi test lagi sekarang**. Output default sudah ada dan dilindungi dari overwrite. Reproduksi terpisah memerlukan lokasi output baru dan konfigurasi yang sesuai. Jangan membandingkan hasil test dari percobaan berulang untuk memilih pengaturan.

Perintah verifikasi kode:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m build
```

Petunjuk instalasi, penempatan CSV, dan perintah `freeze` lengkap ada di [README proyek](../../day1/README.md). Path absolut dalam manifest mengacu pada workspace saat run dibuat. Peta `data/manifests/relocation.json` mengarahkan path lama ke salinan lokal tanpa mengubah manifest atau hash historis.

## 11. Kesimpulan Day 1 dan batas klaim

Fondasi eksperimen sudah tersedia: identitas data jelas, target dan fitur terpisah, preprocessing hanya belajar dari train-fit, model sederhana berhasil dilatih, serta metrik dan asal hasil dapat diaudit. Struktur kode utamanya adalah `src/preprocess.py`, `src/centralized.py`, dan `src/metrics.py`, dengan konfigurasi terpisah dan tes otomatis.

Hasil ini belum membuktikan efisiensi komunikasi, manfaat adaptasi demand, ketahanan terhadap staleness, atau kinerja FL pada pembagian klien non-IID. Belum ada eksperimen untuk mengukur hal-hal tersebut. Hasil satu seed juga belum menggambarkan variasi performa lintas seed.

Catatan terpenting dari baseline: **deteksi serangan tinggi, tetapi alarm palsu pada trafik Normal masih cukup besar**. Temuan ini dicatat sebagai keterbatasan run tetap, bukan alasan untuk menyesuaikan model menggunakan test resmi. Pekerjaan berhenti pada Day 1.

### Sumber internal rekap

- [Konfigurasi model](../../../configs/day1_model.yaml) dan [eksperimen](../../../configs/day1_experiments.yaml).
- [Hasil evaluasi dan metadata lengkap](../../../results/processed/centralized_seed42_test.json).
- [Manifest dataset](../../../data/manifests/dataset.json) dan [preprocessing](../../../data/manifests/preprocessing.json).
- [Checklist penyelesaian](../../day1/tasks/todo.md).

Rekap ini disusun dari artefak yang sudah tersimpan; tidak menjalankan ulang training atau evaluasi test.
