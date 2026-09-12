# Rencana Teknis Laboratorium DSIC-2907

Dokumen ini adalah protokol eksekusi teknis untuk rencana riset satu bulan DSIC-2907. Isinya menerjemahkan desain penelitian menjadi urutan kerja laboratorium: alasan metodologis, implementasi, pengukuran, artefak, verifikasi, dan quality gate. Dokumen ini bukan naskah tesis dan bukan pengganti [README penelitian utama](../README.md) maupun [dokumentasi Day 1](../paper/day1/README.md).

Protokol ini bersifat falsifiable. B0--B3 boleh tidak mendukung hipotesis awal, tetapi setiap kesimpulan harus berasal dari kondisi berpasangan, log mentah, dan metrik yang sudah ditentukan sebelum hasil utama dibaca. Nilai yang belum dibekukan diberi label \`ditentukan pada pilot\`, \`calibration parameter\`, atau \`belum dibekukan\`.

## 1. Tujuan Dokumen

Dokumen ini menetapkan execution flow untuk satu bulan eksperimen dengan:

- dataset utama UNSW-NB15 dan task binary \`Normal (0)\` versus \`Attack (1)\`;
- backbone Asynchronous Federated Learning dengan 10 logical clients;
- B0 Async-Uniform sebagai baseline kausal;
- B1 Demand-Participation, B2 Demand-Budget, dan B3 Joint Demand-Aware;
- main non-IID condition berupa Dirichlet label skew dengan \`alpha = 0.5\`;
- minimum tiga seed;
- dua actuator adaptif: participation priority/frequency dan update budget;
- local compute yang tetap untuk semua policy;
- pengukuran kualitas model, komunikasi, waktu, staleness, dan partisipasi.

Setiap tahap menjawab lima pertanyaan operasional: mengapa tahap ada, risiko validitas apa yang dikontrol, urutan teknis apa yang dilakukan, artefak apa yang disimpan, dan bukti apa yang harus lulus sebelum tahap berikutnya dimulai.

## 2. Prinsip Eksperimen

1. Isolasi satu sumber variasi pada satu waktu. B1 mengubah participation, B2 mengubah budget, dan B3 mengubah keduanya.
2. Validasi komponen level rendah sebelum eksperimen level tinggi: data dan metrik lebih dahulu, lalu async backbone, byte accounting, state, demand, dan policy.
3. Pertahankan kondisi berpasangan. B0--B3 pada seed yang sama memakai partition, initialization, training setting, concurrency, dan network profile/trace yang sama.
4. Pisahkan \`train-fit\`, \`validation\`, dan final \`test\`. Official test hanya untuk evaluasi final yang sudah dibekukan.
5. Simpan bukti pada level event. Ringkasan run harus dapat diturunkan kembali dari event log.
6. Bekukan konfigurasi sebelum main runs. Threshold, weights, action grid, fairness rule, dan analysis plan tidak boleh diubah setelah melihat hasil utama.
7. Bedakan communication bytes, network transfer time, serialization time, local training time, dan wall-clock time.
8. Jangan pernah tuning menggunakan hasil official test.

## 3. Global Dependency Flow

\`\`\`text
UNSW-NB15
    -> dataset freeze
    -> leakage-safe preprocessing
    -> centralized sanity baseline
    -> Dirichlet client partition
    -> Async B0
    -> server versioning + staleness
    -> byte accounting
    -> update budget
    -> state monitor
    -> demand calibration
    -> demand estimator
    -> B1/B2/B3
    -> pilot
    -> protocol freeze
    -> main runs
    -> heterogeneous profile
    -> statistical analysis
    -> ablation
    -> failure analysis
    -> reproduction
    -> final freeze
\`\`\`

Panah menunjukkan dependency, bukan sekadar urutan kalender. Demand-aware logic tidak boleh dijadikan tempat untuk menyembunyikan bug partition atau async execution. Tahap berikutnya hanya boleh dimulai setelah quality gate tahap sebelumnya lulus. Jika gagal, simpan failure reason, perbaiki sumber masalah, dan ulangi verifikasi pada tahap yang terpengaruh.

# WEEK 1 — Data, Async Backbone, and Measurement

## Day 1 — Dataset verification, preprocessing, dan centralized sanity baseline

### Tujuan

Menetapkan bahwa dataset, label, preprocessing, model dasar, dan metrik dapat bekerja secara konsisten sebelum kompleksitas FL dimasukkan. Baseline terpusat ini menjawab apakah pipeline berikut dapat belajar secara masuk akal:

\`\`\`text
official data -> preprocessing -> model -> metrics
\`\`\`

Ia adalah centralized sanity baseline, bukan causal FL comparison dan bukan bukti bahwa FL akan mencapai performa yang sama.

### Mengapa tahap ini diperlukan

Jika FL langsung diimplementasikan dan performanya buruk, penyebabnya dapat berupa preprocessing yang salah, label tertukar, bug metrik, model yang tidak mampu belajar, partition yang keliru, async logic yang salah, staleness, atau communication policy. Baseline terpusat mengisolasi dataset, preprocessing, model, dan metrics sebelum partition, scheduling, staleness, dan komunikasi diperkenalkan. Dengan demikian, masalah yang ditemukan setelah tahap ini dapat diberi lokasi penyebab yang lebih sempit.

### Risiko yang dikontrol

- test leakage dan preprocessing leakage;
- label leakage melalui \`attack_cat\` atau \`label\`;
- salah pemetaan Normal/Attack;
- metric bug, termasuk threshold dan urutan confusion matrix;
- hasil yang tidak dapat ditelusuri ke source hash, configuration, dan checkpoint;
- klaim bahwa performa centralized membuktikan performa FL.

### Implementasi teknis

Day 1 yang sudah selesai mengikuti flow berikut:

\`\`\`text
official training CSV (175,341)
    -> stratified split, seed 42
    -> train-fit (140,272) + validation (35,069)
    -> fit StandardScaler/OneHotEncoder pada train-fit saja
    -> transform train-fit dan validation
    -> train MLP 192 -> 128 -> 64 -> 1
    -> validation sanity metrics

official testing CSV (82,332)
    -> identity/hash audit
    -> transform memakai pipeline yang telah fit
    -> satu frozen-test evaluation terpisah
\`\`\`

Kontrak data:

\`\`\`text
y = label
Normal = 0
Attack = 1
X excludes: id, attack_cat, label
42 source features -> 192 transformed input features
\`\`\`

Konfigurasi centralized sanity baseline yang telah dijalankan:

\`\`\`yaml
architecture: [192, 128, 64, 1]
dropout: 0.1
optimizer: Adam
learning_rate: 0.001
batch_size: 512
epochs: 10
seed: 42
device: cpu
\`\`\`

Preprocessing dilakukan setelah validation split dibuat karena statistik scaler dan vocabulary encoder tidak boleh dipengaruhi validation. Validation dan test hanya menjalankan \`transform\`. Official test diisolasi dari training dan iterative tuning; hasil frozen-test tidak boleh dipakai untuk memilih epoch, checkpoint, threshold, model, atau hyperparameter.

Artifact provenance disimpan sebagai hash chain:

\`\`\`text
test result JSON
  -> checkpoint SHA256
  -> preprocessing manifest SHA256
  -> dataset manifest SHA256
  -> training/test CSV SHA256
\`\`\`

### Input

- official UNSW-NB15 training/testing CSV pair;
- konfigurasi Day 1;
- source schema dan label contract;
- environment/package versions yang tercatat pada artifact.

### Output / Artefak

- \`data/manifests/dataset.json\` — identitas dataset, schema, label mapping, counts, dan source hashes;
- \`data/processed/split_indices.npz\` — posisi baris train-fit/validation;
- \`data/processed/pipeline.joblib\` — pipeline fit pada train-fit;
- \`data/processed/feature_names.json\` — 192 fitur hasil transformasi dalam urutan tetap;
- \`data/processed/preprocessing_config.json\`;
- \`data/manifests/preprocessing.json\` — fit scope dan hash artefak;
- \`results/raw/centralized_seed42/configuration.json\`;
- \`results/raw/centralized_seed42/model.pt\`;
- \`results/raw/centralized_seed42/training.json\`;
- \`results/processed/centralized_seed42_test.json\` — hasil frozen-test dan provenance;
- dokumentasi Day 1 dan jurnal eksekusi.

State faktual Day 1:

| Item | Nilai |
|---|---:|
| Official training | 175,341 rows |
| Train-fit | 140,272 rows |
| Validation | 35,069 rows |
| Official test | 82,332 rows |
| Source features | 42 |
| Transformed input features | 192 |
| Frozen-test Macro-F1 | 0.834634 |
| Frozen-test Attack Recall | 0.981007 |
| Frozen-test AUPRC / Average Precision | 0.980808 |
| Frozen-test Accuracy | 0.843876 |
| Frozen-test AUROC | 0.973654 |
| Frozen-test Balanced Accuracy | 0.828436 |

### Verifikasi / Test minimum

- cek schema, row counts, label mapping, excluded columns, class counts, dan source hashes;
- cek train-fit dan validation disjoint, exhaustive, dan deterministik;
- cek preprocessing hanya fit pada train-fit dan feature order/dimension tetap;
- cek metric dengan Attack sebagai positive class, threshold \`0.5\`, dan \`Average Precision\` untuk AUPRC;
- audit checkpoint, manifest, configuration, result JSON, dan hash chain;
- inspeksi hasil tersimpan tanpa menjalankan official-test evaluation lagi.

Day 1 telah memiliki automated evidence, lint/format, build, dan hasil frozen-test. Official test tidak boleh dibuka ulang hanya untuk verifikasi README ini.

### Quality Gate

\`Status: COMPLETE\`

Lanjut ke Day 2 hanya jika data identity, split, preprocessing isolation, model sanity, metrics, provenance, dan frozen-test protocol telah terdokumentasi. Hasil centralized hanya menyatakan bahwa fondasi pipeline bekerja; ia tidak menyatakan bahwa implementasi FL sudah benar.

## Day 2 — Dirichlet non-IID client partition

### Tujuan

Membentuk partition client yang deterministik untuk simulated non-IID label skew pada main condition \`alpha = 0.5\`, dengan 10 logical clients. Partition ini menjadi objek eksperimen yang sama untuk B0--B3.

### Mengapa tahap ini diperlukan

Partition baru dibuat setelah centralized pipeline tervalidasi agar masalah distribusi client tidak tercampur dengan bug data atau preprocessing. Dirichlet label skew mengontrol konsentrasi label secara eksplisit, tetapi tidak boleh ditulis sebagai representasi distribusi client dunia nyata.

### Risiko yang dikontrol

- partition menggunakan validation atau official test;
- overlap atau kehilangan baris train-fit;
- perbedaan partition antar-policy yang menjadi confounding;
- random seed variance yang menyamar sebagai policy effect;
- klaim berlebihan bahwa Dirichlet merepresentasikan real-world client distribution.

### Implementasi teknis

Hanya 140,272 posisi \`train-fit\` yang boleh dibagi. Global validation dan official test tetap berada di luar client storage.

Untuk setiap kelas \`c\`:

\`\`\`text
indices_c = indices(train_fit where y == c)
deterministic_shuffle(indices_c, seed_c)
p_c ~ Dirichlet(alpha, ..., alpha)       # 10 proportions
cut points from p_c
allocate indices_c to client_1 ... client_10
\`\`\`

Gabungkan alokasi Normal dan Attack untuk setiap client. \`seed_c\` harus diturunkan secara deterministik dari configured partition seed, tetapi aturan turunannya disimpan dalam manifest.

\`\`\`python
for class_label in [0, 1]:
    class_indices = shuffled_train_fit_indices[y == class_label]
    proportions = dirichlet(alpha=0.5, size=10, seed=partition_seed)
    client_indices = split_by_proportions(class_indices, proportions)

partition = combine_class_allocations(client_indices)
assert union(partition.values()) == train_fit_indices
assert pairwise_intersections_are_empty(partition.values())
assert sum(len(v) for v in partition.values()) == 140272
\`\`\`

### Input

- frozen \`train-fit\` indices dan labels;
- \`num_clients = 10\`;
- \`alpha = 0.5\`;
- configured partition seed;
- preprocessing/feature contract yang sudah tervalidasi.

### Output / Artefak

- \`data/partitions/partition_alpha0.5_seed<seed>.json\`;
- per-client sample count dan class distribution CSV;
- partition manifest dengan dataset/preprocessing hash, seed, alpha, algorithm version, dan client IDs;
- optional class distribution plot;
- checksum partition yang dipakai ulang oleh B0--B3.

### Verifikasi / Test minimum

- \`union(all client indices) == train-fit indices\`;
- \`intersection(client_i, client_j) == empty\` untuk semua \`i != j\`;
- \`sum(client sample counts) == 140272\`;
- tidak ada validation/test index pada client partition;
- seed dan urutan index menghasilkan manifest yang sama saat diulang;
- distribusi class setiap client tercatat dan dapat diaudit.

### Quality Gate

Jangan menjalankan B0 jika tiga invariant indeks, source linkage, seed, dan manifest belum lulus. Day 2 pada dokumen ini adalah prosedur yang menunggu eksekusi; dokumentasinya tidak berarti Day 2 telah dimulai.

## Day 3 — Async-Uniform B0 skeleton

### Tujuan

Membangun baseline kausal B0 dengan asynchronous execution, uniform participation, update budget 100%, dan local compute tetap. B0 harus menjadi backbone yang dipakai untuk membandingkan B1--B3.

### Mengapa tahap ini diperlukan

B0 menyediakan titik pembanding yang memisahkan efek demand policy dari efek async FL. Jika B0 belum valid, perubahan pada B1--B3 tidak dapat ditafsirkan sebagai manfaat atau biaya demand-aware allocation.

### Risiko yang dikontrol

- implementasi asynchronous yang sebenarnya menunggu satu putaran lengkap;
- baseline dan proposed memakai aggregation atau local training berbeda;
- client yang selesai cepat diblokir oleh client lambat;
- pengaruh policy tercampur dengan pengaruh model atau optimizer.

### Implementasi teknis

Lifecycle client:

\`\`\`text
eligible
  -> download current global model v
  -> record model_start_version = v
  -> fixed local training
  -> compute model delta
  -> serialize/send update
  -> server immediately accepts or rejects
  -> server applies accepted update and increments version
\`\`\`

Server tidak menunggu global round. Ilustrasi:

\`\`\`text
time ->       t0       t1       t2       t3       t4
fast C1       download train ------ send ---> apply v1
slow C2       download train -------------------------- send -> apply v2
fast C3                download train --- send -------> apply v3
\`\`\`

B0 memakai uniform participation dan full update budget. Nilai concurrency, evaluation interval, dan detail network profile yang belum dibuktikan melalui pilot diberi status \`belum dibekukan\` atau \`ditentukan pada pilot\`, walaupun scaffold konfigurasi sudah memiliki contoh nilai.

### Input

- valid partition;
- frozen model, optimizer, local epoch, batch size, preprocessing;
- async server/client skeleton;
- policy descriptor B0.

### Output / Artefak

- source/module async backbone;
- B0 configuration snapshot;
- run manifest;
- raw event log client/server;
- server version history;
- periodic global validation curve;
- checkpoint dan summary untuk pilot.

### Verifikasi / Test minimum

- dua client dengan durasi berbeda menghasilkan dua arrival event tanpa barrier global;
- server version meningkat setiap accepted update;
- aggregation rule dan sample weighting konsisten;
- B0 selalu memakai budget \`1.00\`;
- local model, optimizer, epoch, batch size, dan preprocessing sama pada client;
- run dapat diulang dengan seed dan partition yang sama.

### Quality Gate

B0 harus terbukti asynchronous pada event log dan harus memiliki raw evidence yang cukup untuk menurunkan staleness, bytes, validation curve, dan run summary. Jika server menunggu slowest client, berhenti dan perbaiki backbone.

## Day 4 — Server versioning dan staleness

### Tujuan

Menambahkan server model version yang monoton dan menghitung staleness setiap update secara eksplisit.

### Mengapa tahap ini diperlukan

Tanpa versioning, keterlambatan update hanya menjadi dugaan waktu. Versioning membuat staleness menjadi metrik sistem, bagian dari state client, possible demand signal, dan variable untuk failure analysis.

### Risiko yang dikontrol

- update lama diterapkan seolah-olah dibuat dari model terbaru;
- staleness salah karena memakai wall-clock saja;
- slow client tidak dapat dibedakan dari update yang tiba setelah banyak apply;
- demand estimator menerima state yang tidak konsisten.

### Implementasi teknis

Definisi utama:

\\[
\\mathrm{staleness}_i = v_{\\mathrm{arrival}} - v_{\\mathrm{start}}
\\]

Server menyimpan \`global_version\`. Client menyimpan version saat download. Saat update tiba, server mencatat version arrival sebelum apply, menghitung staleness, menerapkan aturan aggregation yang sama, lalu menaikkan version jika update diterima.

\`\`\`text
download:       model_start_version = v_start
arrival:        v_arrival = server.global_version
                staleness = v_arrival - v_start
decision:       accepted/rejected
accepted apply: server.global_version = v_arrival + 1
\`\`\`

### Input

- B0 async skeleton;
- client download/arrival events;
- server version state.

### Output / Artefak

- versioned server state;
- event log fields \`server_version\`, \`model_start_version\`, \`staleness\`;
- staleness summary per run dan per client;
- fast/slow client test fixture dan result.

### Verifikasi / Test minimum

- \`staleness >= 0\` pada semua accepted/rejected arrival;
- fast update yang tiba sebelum apply lain memiliki staleness 0;
- update yang dibuat pada \`v=0\` dan tiba setelah dua apply memiliki staleness 2;
- server version monoton;
- event log dapat direplay untuk merekonstruksi staleness.

### Quality Gate

Rumus, version transition, dan fixture fast/slow harus lulus. Staleness yang hanya dihitung dari timestamp tidak cukup.

## Day 5 — Communication byte accounting

### Tujuan

Mengukur biaya komunikasi pada level byte serialized yang benar-benar dikirim dan diterima, terpisah dari waktu transfer serta waktu komputasi.

### Mengapa tahap ini diperlukan

Tensor density bukan communication cost. Indeks, value, dtype, shape, header, framing, dan metadata dapat membuat retained-parameter ratio berbeda dari byte saving aktual. Klaim efisiensi harus berdasar serialized bytes.

### Risiko yang dikontrol

- klaim \`75% saving\` hanya dari \`25% retained parameters\`;
- upload dan download tercampur;
- serialization time dianggap network time;
- local training time dianggap communication time;
- kompresi atau metadata tidak terukur.

### Implementasi teknis

Untuk setiap transfer simpan:

\`\`\`text
upload_bytes   = exact serialized update payload + protocol framing
download_bytes = exact serialized model payload + protocol framing
total_bytes    = upload_bytes + download_bytes
serialization_time
transfer_time
local_train_time
wall_clock_time
\`\`\`

Ukuran dicatat setelah serialization dan sebelum transport. Jika transport menambah envelope, envelope itu harus dimasukkan dengan definisi yang sama pada semua policy. \`bytes-to-target\` memakai cumulative \`total_bytes\` hingga target validation tercapai.

### Input

- B0 versioned async run;
- serializer/deserializer;
- model payload dan update payload;
- network timing hooks.

### Output / Artefak

- byte accounting module;
- per-transfer byte log;
- upload/download/total byte summary;
- serialization dan transfer timing fields;
- accounting definition pada run manifest.

### Verifikasi / Test minimum

- \`len(serialized_payload)\` sama dengan \`upload_bytes\` yang dilaporkan;
- upload dan download tidak tertukar;
- accounting konsisten untuk dense full update;
- zero/empty/invalid payload ditolak dengan jelas;
- replay run menghasilkan total byte yang sama.

### Quality Gate

Tidak ada communication-efficiency claim sebelum actual serialized upload, download, total bytes, dan overhead tercatat serta dapat diaudit.

## Day 6 — Update budget 25/50/100%

### Tujuan

Menetapkan operator update budget diskret dengan action \`25%\`, \`50%\`, dan \`100%\`, sambil mempertahankan local compute tetap.

### Mengapa tahap ini diperlukan

Action grid diskret mudah diaudit dan cukup untuk eksperimen satu bulan. Budget menjadi actuator komunikasi yang terpisah dari participation. Operator awal ditetapkan sebagai magnitude top-k, bukan algoritma compression baru.

### Risiko yang dikontrol

- local training ikut berubah saat budget berubah;
- reconstruction delta salah;
- top-k tidak deterministik karena tie handling;
- metadata menghapus byte saving;
- rasio parameter disamakan dengan rasio komunikasi.

### Implementasi teknis

Untuk delta tensor dengan \`N\` parameter, retained count untuk budget \`q\` adalah \`k = ceil(qN)\` sesuai aturan yang dibekukan pada operator.

\`\`\`text
full delta
  -> magnitude top-k selection
  -> selected values + flat indices + shape/dtype metadata + header
  -> serialize
  -> deserialize
  -> reconstruct sparse/dense delta of original shape
  -> server aggregation/apply
\`\`\`

Contoh kontrak payload:

\`\`\`text
header: version, tensor_count, dtype, shape, operator, budget
body:   selected_indices, selected_values
\`\`\`

\`25% retained parameters\` tidak otomatis berarti \`75% communication saving\`, karena indeks, header, alignment, framing, dan dtype harus dihitung.

### Input

- full model delta dari fixed local training;
- action grid \`[0.25, 0.50, 1.00]\`;
- operator magnitude top-k;
- serializer contract.

### Output / Artefak

- update-budget operator;
- payload format/version;
- reconstructed delta fixture;
- actual byte report untuk setiap budget;
- deterministic selection test result.

### Verifikasi / Test minimum

- reconstructed tensor memiliki shape dan dtype yang valid;
- budget \`1.00\` mempertahankan semua elemen sesuai kontrak;
- top-k deterministic untuk input dan tie case yang sama;
- nilai selected dan index cocok dengan full delta;
- actual byte reduction diukur, termasuk metadata dan serialization overhead;
- server apply memakai reconstructed delta yang benar.

### Quality Gate

Ketiga action dapat direconstruct dan diterapkan dengan benar, serta byte saving aktual tersedia. Jika budget hanya mengubah label log tanpa mengubah serialized payload, tahap ini gagal.

## Day 7 — Backbone freeze

### Tujuan

Membekukan fondasi teknis sebelum state, demand, dan policy adaptif diperkenalkan.

### Mengapa tahap ini diperlukan

Demand-aware logic mudah menyerap perubahan lain secara tidak sengaja. Freeze memisahkan efek policy dari perubahan model, optimizer, aggregation, concurrency, operator, dan serialization.

### Risiko yang dikontrol

- post-hoc perubahan backbone;
- confounding antar-policy;
- sulitnya mereproduksi pilot dan main runs;
- klaim byte saving dengan payload format berbeda.

### Implementasi teknis

Freeze manifest harus mencatat:

\`\`\`text
model architecture and initialization
optimizer, learning rate, local epoch, batch size
preprocessing and feature order
aggregation rule and staleness handling
client/server concurrency
serialization format and update operator
evaluation definition
\`\`\`

Nilai yang belum diuji melalui pilot ditulis \`ditentukan pada pilot\`; jangan mengubahnya diam-diam selama B1--B3.

### Input

- hasil verifikasi Day 1--6;
- B0 run evidence;
- budget operator dan byte contract.

### Output / Artefak

- Week 1 backbone freeze manifest;
- immutable configuration snapshot;
- test report dan known limitations;
- baseline event-log schema.

### Verifikasi / Test minimum

- hash configuration dan operator tersimpan;
- B0 repeated smoke run memakai komponen identik;
- byte accounting dan staleness bisa direplay;
- tidak ada parameter adaptif yang belum didokumentasikan.

### Quality Gate

Week 2 tidak boleh dimulai sebelum data/partition, async behavior, staleness, byte accounting, dan budget reconstruction seluruhnya valid.

# WEEK 2 — State, Demand, and Policy Construction

## Day 8 — Workload/state monitoring

### Tujuan

Menyediakan observasi client yang konsisten untuk demand estimator tanpa mencampur state, interpretasi demand, dan action.

### Mengapa tahap ini diperlukan

Jika estimator membaca action yang sudah dipilih, terjadi circularity. Pemisahan state dan demand diperlukan agar mekanisme dapat ditelusuri serta diuji sebagai \`observation -> interpretation -> decision\`.

### Risiko yang dikontrol

- state dan action tercampur;
- leakage dari future event;
- fitur tidak tersedia pada saat keputusan dibuat;
- data heterogeneity dan system heterogeneity sulit dipisahkan.

### Implementasi teknis

State client yang dipantau:

\\[
x_i(t) = [n_i, T_{prev}, RTT_i, BW_i, staleness_i, age_i]
\\]

Makna field:

| Field | Arti operasional |
|---|---|
| \`n_i\` | jumlah sampel client |
| \`T_prev\` | durasi local training sebelumnya |
| \`RTT_i\` | round-trip latency terukur/tersimulasi |
| \`BW_i\` | bandwidth/throughput terukur/tersimulasi |
| \`staleness_i\` | version lag update terakhir/arrival saat ini |
| \`age_i\` | waktu/event sejak partisipasi terakhir |

\`\`\`text
state = observation at decision time
demand = interpretation of state
action = participation level and/or update budget
\`\`\`

### Input

- B0 event log;
- client metadata, timing, version state;
- controlled network profile.

### Output / Artefak

- state monitor;
- state snapshot/event fields;
- state schema dan availability timestamp;
- missing/invalid observation report.

### Verifikasi / Test minimum

- setiap state field memiliki asal dan waktu observasi;
- state sebelum action tidak menggunakan event masa depan;
- staleness dan age konsisten dengan version/participation history;
- client dengan sample count berbeda tidak kehilangan state.

### Quality Gate

State vector dapat direplay dari event log dan terpisah secara eksplisit dari demand serta action.

## Day 9 — Calibration runs

### Tujuan

Mengukur skala dan distribusi state agar input demand dapat dinormalisasi secara bertanggung jawab.

### Mengapa tahap ini diperlukan

\`n_i\`, seconds, milliseconds, bandwidth, staleness, dan age berada pada unit berbeda. Menjumlahkan raw values dapat membuat satu fitur mendominasi tanpa alasan metodologis. Calibration harus terjadi sebelum main runs.

### Risiko yang dikontrol

- dominasi unit atau outlier;
- normalization yang memakai official-test performance;
- calibration setelah melihat hasil B0--B3;
- demand threshold yang berubah post-hoc.

### Implementasi teknis

Jalankan calibration pada state/logging path yang sama dengan eksperimen, menggunakan data yang diizinkan dan tanpa membaca official-test score untuk memilih parameter. Simpan untuk tiap fitur:

\`\`\`text
min, max, median, p05, p25, p75, p95, variance/robust spread
\`\`\`

Normalisasi dan clipping, jika dipakai, harus memiliki formula dan sumber statistik yang tersimpan. Calibration output menjadi input immutable untuk demand estimator setelah protocol freeze.

### Input

- state snapshots dari smoke/pilot calibration;
- training/validation-side operational observations;
- controlled profiles dan seed/partition metadata.

### Output / Artefak

- \`calibration.json\` atau format setara;
- normalization parameters;
- distribution summary/plot;
- calibration provenance dan hash.

### Verifikasi / Test minimum

- semua field memiliki statistik dan satuan;
- transform normalisasi deterministik;
- missing/out-of-range behavior tercatat;
- official-test metrics tidak menjadi input calibration;
- calibration artifact dapat dipakai ulang pada paired runs.

### Quality Gate

Formula normalisasi dan sumber statistik sudah ditentukan; weights dan thresholds demand masih boleh \`ditentukan pada pilot\` sampai Day 14.

## Day 10 — Demand estimator

### Tujuan

Mengubah state ter-normalisasi menjadi dua keluaran transparan: \`d_part\` untuk participation dan \`d_budget\` untuk update budget.

### Mengapa tahap ini diperlukan

Participation dan budget adalah actuator berbeda. Satu scalar campuran akan menyulitkan interpretasi apakah penghematan berasal dari peluang ikut atau payload yang lebih kecil. Estimator transparan lebih sesuai untuk scope satu bulan daripada reinforcement learning yang menambah ruang tuning dan confounding.

### Risiko yang dikontrol

- demand scalar menyembunyikan mekanisme;
- policy tidak bisa diisolasi pada B1/B2;
- RL/scheduler belajar dari official-test atau outcome masa depan;
- keputusan tidak dapat direplay.

### Implementasi teknis

Definisi interface:

\\[
D_i(t) = [d_{part}, d_{budget}]
\\]

Salah satu bentuk transparan yang boleh dipakai adalah normalized scoring:

\`\`\`python
z = normalize(state, calibration)
d_part = clip(sum(w_part[j] * z[j] for j in features), 0, 1)
d_budget = clip(sum(w_budget[j] * z[j] for j in features), 0, 1)
\`\`\`

Formula, sign setiap fitur, weights, clipping, dan mapping ke action harus ditulis pada pilot manifest. Nilai tersebut belum dibekukan sebelum Day 14. Demand hanya memakai state yang tersedia saat keputusan dibuat.

### Input

- state vector;
- calibration parameters;
- estimator formula candidate;
- candidate weights/thresholds yang berstatus \`belum dibekukan\`.

### Output / Artefak

- demand estimator;
- demand formula document;
- \`d_part\`/\`d_budget\` pada event log;
- mapping trace state -> demand.

### Verifikasi / Test minimum

- deterministic output untuk state yang sama;
- output berada pada domain yang disepakati;
- feature contribution dapat dijelaskan;
- tidak ada future label atau official-test metric dalam input;
- perturbasi satu fitur menghasilkan arah perubahan sesuai formula.

### Quality Gate

Estimator dapat direplay dan outputnya terpisah. Formula final, weights, thresholds, dan action mapping belum dianggap frozen sebelum pilot selesai.

## Day 11 — B1 dan B2

### Tujuan

Membuat dua ablation policy yang hanya mengaktifkan satu actuator pada satu waktu.

### Mengapa tahap ini diperlukan

B1 dan B2 adalah syarat interpretasi kausal B3. Tanpa ablation, peningkatan atau penghematan B3 tidak dapat dipisahkan menjadi contribution dari participation, budget, atau interaksi keduanya.

### Risiko yang dikontrol

- policy isolation failure;
- perubahan model/local compute yang tersembunyi;
- joint effect disalahartikan sebagai efek satu actuator;
- hasil B3 dipilih karena paling baik tanpa baseline decomposition.

### Implementasi teknis

\`\`\`text
B0: uniform participation + fixed 100% budget
B1: demand-aware participation + fixed 100% budget
B2: uniform participation + demand-aware 25/50/100% budget
B3: demand-aware participation + demand-aware budget
\`\`\`

B1 mengisolasi causal effect participation. B2 mengisolasi causal effect update budget. B3 menguji joint mechanism.

### Input

- frozen backbone;
- demand estimator candidate;
- budget operator;
- policy descriptors.

### Output / Artefak

- B1/B2 configuration snapshots;
- policy isolation report;
- unit/smoke event logs;
- comparison matrix terhadap B0.

### Verifikasi / Test minimum

- B1 hanya mengubah participation fields/action;
- B1 budget selalu \`1.00\`;
- B2 participation uniform;
- B2 hanya mengubah budget action;
- model, optimizer, local training, aggregation, concurrency, partition, dan profile sama.

### Quality Gate

Policy diff report harus menunjukkan tepat actuator yang diizinkan. Perubahan lain menghentikan pilot sampai diperbaiki.

## Day 12 — B3 dan fairness guardrail

### Tujuan

Menggabungkan adaptive participation dan adaptive update budget dalam B3 sambil mencegah client starvation.

### Mengapa tahap ini diperlukan

Joint policy berpotensi mengoptimalkan byte cost dengan mengabaikan client tertentu, terutama pada non-IID. Fairness floor memastikan efisiensi tidak dicapai melalui suppression client yang membawa distribusi label penting.

### Risiko yang dikontrol

- client starvation dan fast-client domination;
- rare-client suppression pada label skew;
- staleness explosion;
- budget terlalu rendah pada update yang penting;
- B3 berubah menjadi scheduler tanpa guardrail.

### Implementasi teknis

\`\`\`text
state
  -> demand
  -> participation controller
  -> budget controller
  -> fixed local training
  -> budgeted update
  -> async aggregation
\`\`\`

Definisikan maximum inactivity window atau fairness floor secara eksplisit, tetapi nilainya berstatus \`ditentukan pada pilot\` sampai Day 14. Ketika client melewati floor, controller memberi forced eligibility/participation sesuai aturan yang dibekukan. Catat alasan override sebagai event, bukan menghapusnya dari log.

### Input

- B0--B2 policy contract;
- state/demand estimator;
- fairness rule candidate;
- budget action grid.

### Output / Artefak

- B3 policy implementation;
- fairness guardrail configuration;
- action decision log termasuk forced participation;
- starvation/fairness summary per client.

### Verifikasi / Test minimum

- client tidak dapat inactive melebihi guardrail pada fixture;
- forced action tercatat dan dapat dibedakan dari demand action;
- B3 mengubah kedua actuator, local compute tetap;
- action dan update tetap valid saat state ekstrem;
- staleness dan participation share terukur.

### Quality Gate

B3 tidak boleh masuk main run jika fairness rule tidak bisa dibuktikan pada fixture atau client tertentu hilang dari log.

## Day 13 — Pilot B0--B3

### Tujuan

Memvalidasi integrasi B0--B3 secara teknis pada satu seed, satu partition, dan satu network profile.

### Mengapa tahap ini diperlukan

Pilot adalah tempat untuk menemukan bug implementasi, bukan untuk menarik kesimpulan statistik. Ia memberi kesempatan memperbaiki logging, mapping, dan fairness sebelum configuration freeze.

### Risiko yang dikontrol

- policy isolation yang gagal hanya pada runtime;
- event log hilang atau tidak lengkap;
- byte accounting tidak cocok dengan payload;
- demand mapping tidak konsisten;
- reproducibility dan starvation bug.

### Implementasi teknis

\`\`\`text
one seed + one frozen partition + one profile
    -> run B0
    -> run B1
    -> run B2
    -> run B3
    -> inspect event logs and validation curves
\`\`\`

Gunakan pilot untuk menguji demand-to-action mapping, accepted/rejected updates, staleness, bytes, time components, dan fairness. Jangan memilih formula karena official-test result.

### Input

- Week 1 frozen backbone;
- candidate demand/policy;
- one seed and one partition;
- one normal profile.

### Output / Artefak

- empat pilot run directories;
- raw event logs;
- pilot validation curves;
- policy isolation diff;
- pilot issue/failure ledger;
- calibration and protocol freeze proposal.

### Verifikasi / Test minimum

- B0--B3 menyelesaikan lifecycle client/server;
- seluruh required event fields terisi;
- byte totals dapat direkonsiliasi;
- demand -> action mapping dapat direplay;
- fairness override dan staleness muncul pada fixture yang sesuai;
- seed/pairing metadata benar.

### Quality Gate

Semua issue pilot harus resolved atau diberi failure reason yang jelas. Tidak boleh membuat main run untuk menutupi issue yang belum dipahami.

## Day 14 — Protocol freeze

### Tujuan

Membekukan semua keputusan yang dapat memengaruhi perbandingan utama sebelum main runs dimulai.

### Mengapa tahap ini diperlukan

Mengubah weights, thresholds, target, fairness rule, atau evaluation interval setelah melihat hasil utama adalah post-hoc tuning. Protocol freeze menjadikan hasil falsifiable dan melindungi paired comparison.

### Risiko yang dikontrol

- post-hoc parameter tuning;
- cherry-picking policy/seed;
- action grid yang berubah antar-run;
- analysis plan yang mengikuti hasil.

### Implementasi teknis

Freeze manifest harus memuat:

\`\`\`text
demand formula, normalization, weights, thresholds
action grid and budget operator
fairness rule / maximum inactivity window
concurrency and scheduling semantics
evaluation interval
predefined Macro-F1 target
analysis plan and practical criteria
\`\`\`

Concurrency, thresholds, demand weights, maximum inactivity window, heterogeneous RTT/bandwidth, evaluation interval, dan Macro-F1 target tidak diberi nilai final di README ini. Masing-masing berstatus \`ditentukan pada pilot\`/ \`calibration parameter\`/ \`belum dibekukan\` sampai disetujui dalam protocol freeze.

### Input

- pilot artifacts;
- calibration summary;
- issue ledger;
- research design dan policy definitions.

### Output / Artefak

- immutable protocol manifest;
- hashes untuk configs, calibration, partition, serializer, dan policy;
- preregistered practical criteria;
- approved event-log schema;
- signed/recorded freeze decision.

### Verifikasi / Test minimum

- rerun pilot dari manifest menghasilkan action dan log schema yang sama;
- policy diff B0--B3 lulus;
- target dan criteria terisi sebelum main result analysis;
- tidak ada config field penting yang unresolved tanpa label status.

### Quality Gate

Main runs hanya boleh dimulai setelah demand mapping, fairness, policy isolation, reproducibility, dan protocol freeze lulus.

# WEEK 3 — Main Experiments

## Day 15--18 — Main B0--B3 comparison

### Tujuan

Menghasilkan perbandingan utama pada main condition dengan minimum \`4 policies × 3 seeds = 12 paired runs\`.

### Mengapa tahap ini diperlukan

Perbandingan berpasangan mengurangi noise dari partition dan initialization. Pada seed yang sama, perubahan outcome lebih layak diatribusikan ke policy karena kondisi dasar dipertahankan.

### Risiko yang dikontrol

- random seed variance;
- confounding dari partition, model, preprocessing, local training, concurrency, atau network trace;
- iterative tuning menggunakan official test;
- ringkasan yang tidak dapat ditelusuri ke event.

### Implementasi teknis

Main condition:

\`\`\`text
dataset: UNSW-NB15
task: Normal vs Attack
clients: 10 logical clients
alpha: 0.5
profile: normal network profile
policies: B0, B1, B2, B3
seeds: minimum 3
\`\`\`

Untuk setiap seed, B0--B3 memakai partition, initialization, preprocessing, model, optimizer, local epoch, batch size, aggregation, concurrency, network profile/trace, dan evaluation definition yang sama. Global validation dilakukan periodik sesuai interval yang sudah dibekukan. Official test tetap frozen dan tidak dipakai untuk iterative evaluation.

Event log minimum:

| Field | Fungsi |
|---|---|
| \`run_id\`, \`policy\`, \`seed\` | identitas run |
| \`server_version\`, \`client_id\` | konteks event |
| \`model_start_version\`, \`staleness\` | version lag |
| \`num_samples\`, \`local_train_sec\` | data dan compute |
| \`RTT\`, \`bandwidth/throughput\` | sistem/network |
| \`age\` | recency client |
| \`demand_part\`, \`demand_budget\` | estimator output |
| \`participation_level\`, \`update_budget\` | selected action |
| \`upload_bytes\`, \`download_bytes\`, \`total_bytes\` | communication |
| \`serialization_time\`, \`transfer_time\` | time decomposition |
| \`accepted/rejected\`, \`reject_reason\` | server outcome |

### Input

- frozen protocol manifest;
- frozen partition per seed;
- model/preprocessing/backbone;
- normal network profile;
- seed schedule dan policy matrix.

### Output / Artefak

- 12 run manifests;
- raw event logs;
- periodic validation metrics/curves;
- checkpoints sesuai protocol;
- per-run resource accounting;
- status ledger dan failure reasons.

### Verifikasi / Test minimum

- seluruh run memiliki paired condition metadata;
- official test tidak diakses selama training/iterative validation;
- semua event fields hadir atau memiliki missing reason;
- B0--B3 policy isolation tetap benar pada runtime;
- run failure tidak dihapus dan tidak diganti diam-diam;
- seed count minimum terpenuhi.

### Quality Gate

Main alpha \`0.5\` belum lengkap sebelum B0--B3 untuk minimum tiga seed memiliki raw logs, validation curves, manifest, dan status yang dapat diaudit.

## Day 19--21 — Heterogeneous system/network profile

### Tujuan

Menjawab pertanyaan sekunder apakah manfaat B3 berubah ketika heterogeneity sistem/network diperkuat.

### Mengapa tahap ini diperlukan

Demand-aware scheduling memiliki makna sistemik hanya jika state seperti latency, throughput, dan staleness memengaruhi keputusan. Profile heterogen menguji kondisi itu dengan menjaga data dan policy tetap.

### Risiko yang dikontrol

- data heterogeneity tercampur dengan system heterogeneity;
- alpha berubah bersamaan dengan RTT/bandwidth;
- policy definition atau model ikut berubah;
- angka profile dipilih setelah hasil terlihat.

### Implementasi teknis

Gunakan kelas konseptual fast, medium, dan slow client. Nilai RTT/bandwidth final adalah \`ditentukan pada pilot\` dan harus disimpan dalam profile manifest. Hanya controlled system/network condition yang diubah:

\`\`\`text
data partition: fixed
policy definition: fixed
model/training: fixed
system/network profile: controlled change
\`\`\`

Jangan mengubah \`alpha\` pada comparison ini. Bandingkan profile normal dan heterogeneous sebagai analisis sekunder.

### Input

- protocol freeze;
- same partition/seed matrix;
- normal-profile main runs;
- heterogeneous profile candidate.

### Output / Artefak

- network profile manifest dan hash;
- heterogeneous B0--B3 runs/logs;
- per-client RTT/throughput evidence;
- profile comparison summary.

### Verifikasi / Test minimum

- data partition hash sama dengan paired normal run;
- model/training/policy hash sama;
- observed timing berada dalam profile contract atau deviation dicatat;
- heterogeneity tidak diimplementasikan sebagai perubahan alpha;
- fast/medium/slow membership tercatat.

### Quality Gate

Week 3 gate lulus jika B0--B3 alpha \`0.5\` minimum tiga seed lengkap dalam paired condition. Optional extensions menunggu gate ini.

# WEEK 4 — Aggregation, Statistics, Ablation, and Reproduction

## Day 22 — Run-level summaries

### Tujuan

Mengubah event log menjadi satu observasi summary per run/seed/policy.

### Mengapa tahap ini diperlukan

Update events dalam satu run saling bergantung dan bukan statistical replicates independen. Menganggapnya sebagai sampel terpisah menghasilkan pseudo-replication dan confidence interval yang terlalu optimistis.

### Risiko yang dikontrol

- pseudo-replication pada update-event level;
- run failure tersembunyi;
- final quality dipisahkan dari cost/time;
- summary tidak cocok dengan raw log.

### Implementasi teknis

Agregasikan hanya setelah event log tervalidasi. Simpan unit analisis \`run_id\` dan \`seed\`.

### Input

- raw event logs;
- validation curves;
- run manifests dan status ledger.

### Output / Artefak

Run-level table berisi:

- final Macro-F1, Attack Recall, AUPRC/Average Precision;
- total upload bytes, download bytes, total bytes;
- mean/median/p95 staleness;
- participation share;
- bytes-to-target dan time-to-target;
- accepted update count dan failure reason.

### Verifikasi / Test minimum

- total bytes sama dengan penjumlahan event yang masuk scope;
- participation share memakai denominator yang terdokumentasi;
- staleness summary dapat direkonsiliasi;
- satu row summary merepresentasikan satu run, bukan satu update.

### Quality Gate

Semua outcome utama dapat diturunkan dari raw logs dan setiap run memiliki status lengkap.

## Day 23 — Bytes-to-target dan time-to-target

### Tujuan

Mengukur resource yang dibutuhkan untuk mencapai kualitas yang sudah ditentukan.

### Mengapa tahap ini diperlukan

Final Accuracy atau final Macro-F1 saja tidak menunjukkan biaya menuju kualitas tersebut. \`bytes-to-target\` dan \`time-to-target\` menghubungkan quality dengan komunikasi dan wall-clock.

### Risiko yang dikontrol

- target dipilih setelah melihat curve;
- run yang belum mencapai target diperlakukan sebagai zero cost;
- network time disamakan dengan local compute;
- final score tinggi dengan biaya tidak terlihat.

### Implementasi teknis

Target adalah validation Macro-F1 yang dibekukan sebelum main-result analysis. Definisi:

\`\`\`text
first validation event/time where Macro-F1 >= predefined target
    -> cumulative upload bytes
    -> cumulative download bytes
    -> cumulative total bytes
    -> wall-clock time
    -> accepted update count
\`\`\`

Run yang tidak mencapai target diberi status censored/not-reached dengan aturan analisis yang sudah dibekukan.

### Input

- validation curves;
- event timestamps dan byte fields;
- frozen Macro-F1 target.

### Output / Artefak

- bytes-to-target table;
- time-to-target table;
- target reachability report;
- figure/curve dengan target line.

### Verifikasi / Test minimum

- first crossing dipilih secara deterministik;
- cumulative bytes tidak menghitung event setelah crossing;
- target bukan hasil tuning dari official test;
- not-reached run tidak diberi nilai palsu.

### Quality Gate

Target dan aturan not-reached telah tercatat sebelum hasil comparison disimpulkan.

## Day 24 — Paired statistical analysis

### Tujuan

Menganalisis perbedaan B0--B3 pada level run/seed dengan uncertainty yang sesuai.

### Mengapa tahap ini diperlukan

Minimum tiga seed memberi repeated paired observations. Paired analysis memanfaatkan perbedaan dalam seed yang sama dan menghindari klaim dari satu seed terbaik.

### Risiko yang dikontrol

- cherry-picking seed;
- confidence interval dari event pseudo-replicates;
- non-inferiority threshold yang berubah setelah melihat hasil;
- practical target disalahartikan sebagai expected outcome.

### Implementasi teknis

Untuk pasangan policy \`A\` dan \`B\`, hitung:

\`\`\`text
delta_s = metric(B, seed=s) - metric(A, seed=s)
mean(delta), median(delta), std(delta), 95% CI
\`\`\`

Gunakan paired bootstrap pada unit run/seed, bukan event update. Catat jumlah seed, missing run, bootstrap seed, dan interval method.

Practical criteria yang dipra-registrasikan:

\\[
\\text{Non-inferiority: lower 95\\% CI of Macro-F1}(B3-B0) > -0.01
\\]

\\[
\\frac{B0\\ bytes - B3\\ bytes}{B0\\ bytes} \\ge 0.15
\\]

\\[
\\frac{B3\\ TTT - B0\\ TTT}{B0\\ TTT} \\le 0.10
\\]

Ini adalah kriteria praktis yang dibekukan sebelum analisis, bukan hasil yang diasumsikan. Jika tidak terpenuhi, laporkan hasil apa adanya.

### Input

- run-level summary table;
- paired seed mapping;
- frozen criteria dan analysis plan.

### Output / Artefak

- paired differences;
- mean/median/std/95% CI table;
- paired bootstrap output;
- non-inferiority dan communication/time guardrail report.

### Verifikasi / Test minimum

- pasangan benar berdasarkan seed dan kondisi;
- setiap metric memakai denominator dan scope yang sama;
- bootstrap unit adalah run/seed;
- semua seed tersedia atau missingness dijelaskan.

### Quality Gate

Tidak ada kesimpulan utama sebelum raw-to-summary lineage, pairing, uncertainty, dan practical criteria dapat diaudit.

## Day 25 — Ablation analysis

### Tujuan

Menguraikan kontribusi participation, update budget, dan joint mechanism.

### Mengapa tahap ini diperlukan

Perbandingan B3 versus B0 saja tidak cukup untuk causal interpretation. Ablation menunjukkan apakah perubahan berasal dari satu actuator atau interaksi keduanya.

### Risiko yang dikontrol

- B3 diberi kredit untuk effect yang sebenarnya berasal dari B1/B2;
- single actuator tidak diuji;
- kualitas ditukar dengan bytes tanpa Pareto view.

### Implementasi teknis

Interpretasi yang harus dipertahankan:

\`\`\`text
B1 - B0 = participation contribution
B2 - B0 = update-budget contribution
B3 - B0 = joint effect
\`\`\`

Buat Pareto analysis dengan sumbu communication cost, time-to-target, dan Macro-F1. Jangan menyimpulkan B3 menang hanya karena satu metrik.

### Input

- paired B0--B3 summaries;
- statistical analysis output;
- policy isolation manifest.

### Output / Artefak

- ablation table/figure;
- Pareto plot atau table;
- actuator contribution narrative berbasis data.

### Verifikasi / Test minimum

- B1/B2 tetap sesuai isolasi;
- Pareto points memakai seed aggregation yang sama;
- trade-off dan dominated policy dicatat tanpa cherry-pick.

### Quality Gate

Discussion tidak boleh menyebut joint benefit tanpa menunjukkan B1 dan B2.

## Day 26 — Failure analysis

### Tujuan

Menjelaskan mekanisme dan batas kegagalan melalui trace dari state hingga outcome.

### Mengapa tahap ini diperlukan

Rata-rata dapat menyembunyikan starvation, staleness, metadata overhead, atau demand misclassification. Failure analysis memperkuat penjelasan ilmiah dan menunjukkan kapan policy tidak aman dipakai.

### Risiko yang dikontrol

- fast-client domination;
- starvation atau rare-client suppression;
- staleness explosion;
- under-budgeting/over-budgeting;
- metadata/serialization overhead;
- demand misclassification;
- network-profile deviation.

### Implementasi teknis

Jika data memungkinkan, inspeksi minimal 20 extreme/failure events. Untuk setiap event telusuri:

\`\`\`text
state -> demand -> action -> staleness/bytes -> model/system outcome
\`\`\`

Kategori inspeksi:

1. fast-client domination;
2. starvation;
3. staleness explosion;
4. under-budgeting;
5. over-budgeting;
6. metadata overhead;
7. demand misclassification;
8. rare-client suppression;
9. serialization overhead;
10. network-profile deviation.

### Input

- event logs;
- state/demand/action traces;
- failure ledger dan run summaries.

### Output / Artefak

- inspected-event table;
- category counts;
- trace plots/records;
- root-cause notes dan limitation list.

### Verifikasi / Test minimum

- setiap inspected event memiliki \`run_id\`, \`client_id\`, dan timestamp/version;
- trace tidak mengandalkan inferred value tanpa label;
- minimum 20 event dicapai jika data memungkinkan, atau alasan kekurangan dicatat;
- failure categories tidak dihapus hanya karena merusak average.

### Quality Gate

Failure analysis harus dapat menjelaskan setidaknya kejadian ekstrem utama dan menyatakan limitation yang tersisa.

## Day 27--28 — Paper preparation

### Tujuan

Menyusun hasil eksperimen menjadi bagian Method, Experimental Setup, Results, Discussion, dan Threats to Validity.

### Mengapa tahap ini diperlukan

Dokumentasi ilmiah harus mengikuti data yang sudah dianalisis. Results/Discussion baru boleh difinalkan setelah run-level summary, statistics, ablation, dan failure analysis selesai.

### Risiko yang dikontrol

- narasi mendahului evidence;
- centralized sanity baseline ditulis sebagai FL result;
- B3 ditulis sebagai pemenang yang pasti;
- limitation dan threats to validity dihilangkan.

### Implementasi teknis

Introduction/Related Work mungkin sudah ada. Fokus tahap ini:

\`\`\`text
Method
  -> Experimental Setup
  -> Results
  -> Discussion
  -> Threats to Validity
\`\`\`

Tuliskan dataset, partition, paired protocol, event schema, byte definition, metrics, statistical unit, dan negative/unsupported findings secara eksplisit.

### Input

- frozen protocol;
- run-level results, statistics, ablation, failure analysis;
- paper structure yang sudah ada.

### Output / Artefak

- updated method/setup/results/discussion sections;
- tables/figures dengan source data;
- threats-to-validity notes;
- claim-to-evidence map.

### Verifikasi / Test minimum

- setiap angka memiliki source table/log;
- claim tidak melampaui observed condition;
- no-test-tuning dan simulated-non-IID limitations tertulis;
- B3 tidak diasumsikan menang.

### Quality Gate

Naskah Results/Discussion hanya menggunakan output yang sudah melalui analysis gate.

## Day 29 — Fresh reproduction

### Tujuan

Menguji bahwa setidaknya satu main table atau figure dapat diregenerasi dari environment fresh dan artifact yang terdokumentasi.

### Mengapa tahap ini diperlukan

Cached/manual artifact dapat menyembunyikan dependency, path, atau transform yang hilang. Fresh reproduction menguji rantai eksekusi yang akan dipakai pembaca atau peneliti berikutnya.

### Risiko yang dikontrol

- hasil hanya bisa dibuat dari workspace pribadi;
- file cache/manual edit;
- config atau manifest yang tidak lengkap;
- provenance yang tidak cukup untuk regenerasi.

### Implementasi teknis

Target operasional:

\`\`\`text
fresh environment
  -> one documented command
  -> read raw/processed experiment artifacts
  -> regenerate >= one main table or figure
  -> compare with frozen version
\`\`\`

Dataset besar boleh disediakan melalui documented path/manifest sesuai aturan repository, tetapi source hashes dan environment contract harus diverifikasi.

### Input

- Git commit/config hashes;
- raw logs, processed summaries, manifests;
- clean/fresh environment.

### Output / Artefak

- reproduction log;
- regenerated table/figure;
- environment and command record;
- discrepancy report jika ada.

### Verifikasi / Test minimum

- command berjalan tanpa manual editing;
- output memiliki source lineage;
- perbedaan numerik dijelaskan oleh tolerance/environment bila ada;
- reproduction tidak mengubah frozen artifacts.

### Quality Gate

Minimal satu output utama dapat diregenerasi atau blocker reproducibility didokumentasikan sebelum final freeze.

## Day 30 — Final research freeze

### Tujuan

Membekukan seluruh state yang diperlukan untuk audit, publikasi, dan reproduksi.

### Mengapa tahap ini diperlukan

Tanpa final freeze, konfigurasi, log, atau figure dapat berubah setelah kesimpulan ditulis. Experiment ledger menjadikan status run dan alasan failure dapat ditelusuri.

### Risiko yang dikontrol

- hidden rerun;
- perubahan config setelah hasil dipilih;
- raw logs tertimpa;
- run terbaik dipilih tanpa menyimpan seed lain;
- hasil tidak cocok dengan Git commit.

### Implementasi teknis

Freeze:

\`\`\`text
Git commit
configs and hashes
dataset manifest
partition manifests
network profiles
raw event logs
processed summaries
figures
manuscript
\`\`\`

Experiment ledger minimum:

| Field | Isi |
|---|---|
| \`run_id\` | identifier unik |
| \`policy\` | B0/B1/B2/B3 |
| \`seed\` | seed run |
| \`status\` | complete/failed/not-reached |
| \`failure_reason\` | alasan eksplisit jika gagal |
| \`git_commit\` | source state |
| \`config_hash\` | configuration identity |

### Input

- seluruh Week 1--4 artifacts;
- reproduction result;
- final manuscript/figures.

### Output / Artefak

- final Git commit/tag sesuai workflow repository;
- immutable artifact bundle;
- experiment ledger;
- final hashes dan manifest index;
- reproducible analysis command.

### Verifikasi / Test minimum

- ledger mencakup semua planned run;
- raw-to-summary hashes cocok;
- figure/table source dapat ditemukan;
- no hidden rerun atau overwrite tanpa reason log;
- final research gate terpenuhi.

### Quality Gate

Final freeze hanya selesai bila B0--B3, minimum tiga seed, actual bytes, target endpoints, quality metrics, staleness, participation, ablation, uncertainty, failure analysis, dan reproduction evidence tersedia.

# Quality Gates

## Week 1 Gate

Jangan lanjut ke demand-aware work jika:

- Day 1 data pipeline valid dan provenance dapat ditelusuri;
- partition valid sesuai semua invariant;
- B0 asynchronous behavior tervalidasi;
- staleness benar melalui server versioning;
- byte accounting memakai serialized bytes aktual;
- reconstruction update budget 25/50/100% bekerja.

## Week 2 Gate

Jangan menjalankan main experiments jika:

- B1 hanya mengubah participation;
- B2 hanya mengubah budget;
- B3 mengubah keduanya;
- demand mapping sudah frozen;
- fairness guardrail bekerja;
- protocol reproducible.

## Week 3 Gate

Jangan memulai optional extensions jika:

- B0--B3 pada \`alpha = 0.5\` selesai;
- minimum tiga seed selesai;
- paired conditions terjaga;
- raw logs dan validation curves lengkap.

## Week 4 / Research Gate

Minimum completion:

- B0--B3 dan tiga seed;
- actual upload/download/total bytes;
- bytes-to-target dan time-to-target;
- Macro-F1, Attack Recall, AUPRC/Average Precision;
- staleness dan participation share;
- B1/B2 ablation;
- confidence intervals dan non-inferiority analysis;
- failure analysis;
- reproducible analysis command.

# Artefak yang Dihasilkan per Tahap

| Tahap | Input | Output utama | Verification |
|---|---|---|---|
| Day 1 — data dan centralized sanity | official CSV pair, Day 1 config | dataset/preprocessing manifests, pipeline, split indices, checkpoint, frozen-test JSON | schema, split, fit isolation, metrics, provenance |
| Day 2 — partition | train-fit indices, labels, \`alpha=0.5\`, 10 clients | partition JSON, distribution CSV, manifest, checksum | union, disjointness, count 140,272, no validation/test |
| Day 3 — B0 skeleton | valid partition, frozen model/backbone | B0 config, async event log, validation curve | no global barrier, full budget, fixed compute |
| Day 4 — version/staleness | B0 events, server state | version history, staleness fields, fast/slow fixture | \`v_arrival-v_start\`, monotonic version |
| Day 5 — byte accounting | serialized model/update payloads | transfer log, byte/timing summary | exact serialized length, upload/download separation |
| Day 6 — update budget | full delta, top-k operator | payload format, reconstructed tensors, byte report | shape/dtype, deterministic top-k, overhead measured |
| Day 7 — backbone freeze | Day 1--6 evidence | Week 1 freeze manifest | component hashes and replay |
| Day 8 — state monitor | B0 logs, client/system observations | state schema and snapshots | availability time, state/demand/action separation |
| Day 9 — calibration | state snapshots | calibration distributions and normalization artifact | no official-test tuning, deterministic transform |
| Day 10 — demand estimator | normalized state, candidate formula | estimator, \`d_part\`, \`d_budget\`, trace | replayable output, no future input |
| Day 11 — B1/B2 | frozen backbone, estimator, budget operator | B1/B2 configs and isolation report | one actuator changes per ablation |
| Day 12 — B3/fairness | B1/B2 contracts, fairness candidate | B3 config, guardrail logs | no starvation beyond frozen rule |
| Day 13 — pilot | one seed/partition/profile, B0--B3 | four pilot runs, issue ledger | logging, bytes, mapping, fairness, reproducibility |
| Day 14 — protocol freeze | pilot/calibration artifacts | immutable protocol manifest and hashes | all key decisions frozen |
| Day 15--18 — main B0--B3 | frozen protocol, 3 seeds, alpha 0.5 | 12 paired run dirs, raw logs, validation curves | paired metadata and complete status |
| Day 19--21 — heterogeneity | fixed data/policy, controlled profile | heterogeneous profile and runs | only system/network condition changes |
| Day 22 — summaries | raw event logs and curves | run-level table | one row per run; totals reconcile |
| Day 23 — target endpoints | curves, timestamps, frozen target | bytes/time-to-target tables | first crossing and not-reached handling |
| Day 24 — statistics | paired run table | deltas, CI, paired bootstrap | run/seed-level unit |
| Day 25 — ablation | B0--B3 statistics | contribution and Pareto analysis | B1/B2 interpretation preserved |
| Day 26 — failure analysis | event/state/action traces | inspected events, categories, root causes | >=20 if data permit, trace complete |
| Day 27--28 — paper preparation | frozen analysis outputs | method/setup/results/discussion/threats | claim-to-evidence links |
| Day 29 — reproduction | fresh environment, frozen artifacts | reproduction log, regenerated table/figure | one-command path or blocker record |
| Day 30 — final freeze | all artifacts and manuscript | ledger, hashes, final bundle, commit | research gate and no hidden reruns |

# Dependency Matrix

| Stage | Depends on | Blocks |
|---|---|---|
| Dataset freeze | official CSV identity | all preprocessing and partition work |
| Leakage-safe preprocessing | dataset freeze, train-fit split | centralized baseline and client features |
| Centralized sanity baseline | preprocessing, model/metrics | client partition |
| Client partition | validated train-fit pipeline | B0 paired runs |
| Async B0 | partition, frozen model/training | staleness, byte, policy work |
| Versioning/staleness | async B0 | state monitor and failure analysis |
| Byte accounting | serializer and async transfers | communication claims and budget |
| Update budget | byte accounting, full delta | B2/B3 |
| Backbone freeze | Day 1--6 evidence | state/demand work |
| State monitor | B0 events and versioning | calibration and demand |
| Calibration | state monitor, allowed observations | estimator freeze |
| Demand estimator | calibration | B1/B2/B3 |
| B1/B2 | estimator, frozen backbone | B3 interpretation |
| B3/fairness | B1/B2 contracts | pilot |
| Pilot | B0--B3 and profile | protocol freeze |
| Protocol freeze | pilot evidence | main runs |
| Main alpha 0.5 | protocol, partition, seeds | heterogeneity and statistics |
| Heterogeneous profile | main protocol, fixed data/policy | secondary result |
| Run summaries | complete raw logs | target endpoints/statistics |
| Statistical analysis | run-level paired table | claims and paper |
| Ablation/failure analysis | statistics and event traces | discussion and final freeze |
| Fresh reproduction | frozen artifacts | final research freeze |

# Rules That Must Never Be Violated

- Tidak ada tuning menggunakan official-test result.
- Tidak ada partition berbeda untuk paired B0--B3 runs pada seed/condition yang sama.
- Tidak boleh mengubah model atau local compute antar-policy.
- Tidak boleh mengubah network trace/profile antar paired policy runs.
- Tidak boleh ada hidden rerun tanpa reason log.
- Tidak boleh memilih hanya seed terbaik.
- Tidak boleh mengklaim communication reduction dari sparsity ratio saja.
- Tidak boleh mengubah demand thresholds setelah melihat main results.
- Tidak boleh memperlakukan update events sebagai independent statistical replicates.
- Tidak boleh memasukkan \`id\`, \`attack_cat\`, atau \`label\` sebagai model input.
- Tidak boleh membagi global validation atau official test ke client.
- Tidak boleh menyebut centralized sanity score sebagai bukti performa FL.
- Tidak boleh menyebut Dirichlet label skew sebagai representasi distribusi client dunia nyata.
- Tidak boleh menyatakan B3 pasti menang.

# Scope Bulan Pertama

Eksperimen inti bulan pertama secara eksplisit tidak mencakup:

- adaptive local epochs;
- adaptive batch size;
- adaptive CPU/memory;
- RL scheduler;
- new compression algorithm;
- differential privacy;
- secure aggregation;
- poisoning defense;
- multiple NIDS architectures;
- real edge deployment;
- ROAD sebelum core experiment selesai.

Perluasan baru boleh dipertimbangkan setelah Research Gate lulus. Jika core experiment belum lengkap, jangan memulai perluasan yang mengubah sumber variasi utama.

