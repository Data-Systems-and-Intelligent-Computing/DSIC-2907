# DSIC-2907 — Demand-Aware Adaptive Resource Allocation for Asynchronous Federated NIDS

Repositori penelitian **DSIC-2907** untuk menguji apakah *workload* dan kondisi terkini setiap klien dapat dipakai untuk membentuk estimasi *demand*, lalu menggunakan estimasi tersebut untuk mengatur **participation priority/frequency** dan **update budget** pada *Asynchronous Federated Learning* sehingga komunikasi menjadi lebih efisien tanpa menurunkan performa *Network Intrusion Detection System* (NIDS) secara bermakna pada data *non-IID*.

> **Status penelitian:** desain eksperimen dibekukan untuk eksperimen utama satu bulan.  
> **Backbone:** Asynchronous Federated Learning.  
> **Dataset utama:** UNSW-NB15.  
> **Task utama:** binary intrusion detection, `normal` vs `attack`.  
> **Jumlah klien utama:** 10 logical clients.  
> **Main policies:** B0, B1, B2, B3.  
> **Main non-IID setting:** Dirichlet label skew, `alpha = 0.5`.  
> **Minimum repeated runs:** 3 seeds.  
> **Kontribusi utama:** joint demand-conditioned participation dan update budgeting, bukan algoritma asynchronous FL baru dan bukan algoritma sparsification baru.

---

## 1. Keputusan Pembimbing

Penelitian ini **dapat diteruskan**, tetapi desain eksperimennya harus dijaga ketat agar kontribusi yang diukur benar-benar berasal dari mekanisme *demand-aware*.

Baseline dan metode usulan menggunakan:

- arsitektur Asynchronous FL yang sama;
- agregator yang sama;
- model NIDS yang sama;
- dataset dan partition yang sama;
- *local epoch*, *batch size*, optimizer, precision, dan CPU/memory limit yang sama;
- network trace/profile yang sama untuk pasangan eksperimen;
- aturan staleness yang sama.

Perbedaan yang sengaja dibuat hanya:

1. apakah **participation priority/frequency** ditentukan secara uniform atau *demand-aware*;
2. apakah **update budget** ditentukan secara fixed atau *demand-aware*.

Local compute **tidak menjadi actuator utama** pada eksperimen satu bulan. Adaptive local epoch, adaptive batch size, adaptive CPU-memory, dan reinforcement-learning scheduler ditunda sampai eksperimen B0–B3 selesai.

---

## 2. Judul Penelitian

### Judul kerja skripsi

**Optimasi Komunikasi Federated Learning Asinkron untuk Network Intrusion Detection melalui Demand-Aware Adaptive Resource Allocation pada Data Non-IID**

### Judul artikel yang lebih presisi

**Demand-Aware Adaptive Participation and Update Budgeting for Communication-Efficient Asynchronous Federated Network Intrusion Detection under Non-IID Data**

Judul artikel sengaja menyebut dua actuator secara eksplisit supaya istilah *resource allocation* tidak disalahartikan sebagai adaptive CPU-memory allocation.

---

## 3. Kalimat Jangkar Penelitian

> Penelitian ini menguji apakah demand yang dihitung dari workload dan kondisi klien dapat digunakan untuk mengatur frekuensi/prioritas partisipasi dan update budget pada Asynchronous Federated Learning sehingga komunikasi menjadi lebih efisien tanpa menurunkan performa NIDS melebihi margin yang telah ditetapkan pada data non-IID.

Kalimat ini menjadi batas utama penelitian. Bila suatu eksperimen tidak membantu menjawab kalimat tersebut, eksperimen itu bukan prioritas bulan pertama.

---

## 4. Posisi terhadap Katalog DSIC29-07

Katalog awal membahas **pemilihan konfigurasi sumber daya berdasarkan jenis beban**, dengan contoh konfigurasi CPU dan memori. Penelitian ini **bukan replikasi literal** katalog. Prinsip katalog diadaptasi menjadi *workload-conditioned communication-resource configuration* pada Asynchronous FL.

| Konsep katalog | Adaptasi pada DSIC-2907 |
|---|---|
| Jenis beban kerja | keadaan workload per klien: jumlah sampel, local training time, latency, throughput, staleness, dan recency |
| Konfigurasi CPU dan memori | communication-resource configuration: participation priority/frequency dan update budget |
| Alokasi tetap | Async-Uniform dengan aturan partisipasi dan budget yang sama untuk semua klien |
| Pemilihan konfigurasi per beban | Async-Demand-Aware memilih action berdasarkan state/demand klien |
| Klaster kecil | controlled multi-client testbed pada Linux/Docker; small-cluster fisik bersifat perluasan |

Dengan demikian, kontribusi penelitian harus ditulis sebagai **adaptasi konsep workload-conditioned configuration selection**, bukan sebagai implementasi literal katalog CPU-memory.

---

## 5. Kebaruan yang Aman

Komponen berikut **bukan hal baru secara individual** dan tidak boleh diklaim sebagai novelty:

- asynchronous Federated Learning;
- client selection;
- update sparsification;
- resource-aware FL secara umum;
- staleness-aware aggregation;
- capacity-aware client management.

Kebaruan yang lebih defensible adalah:

> **Evaluasi terkontrol satu demand-estimation module yang secara bersama mengatur participation opportunity dan update budget pada Asynchronous FL-NIDS, dengan backbone async yang identik antara baseline dan proposed, ablation per actuator, byte-accurate communication accounting, dan quality guardrail pada simulated non-IID.**

Kontribusi minimal yang harus terlihat pada artikel:

1. mendefinisikan *client workload/state vector* yang dapat diamati tanpa mengirim raw client data;
2. membangun satu *demand-estimation module* dengan dua keluaran: `d_part` dan `d_budget`;
3. membandingkan baseline dan proposed pada backbone Asynchronous FL yang identik;
4. memisahkan efek participation dan update budgeting melalui B1/B2;
5. mengukur penghematan komunikasi menggunakan **serialized bytes aktual**, bukan density tensor atau wall-clock saja;
6. mengevaluasi trade-off antara communication cost, staleness, time-to-target, fairness, dan kualitas model;
7. menyediakan config, seed, partition manifest, network profile, dan raw event log yang dapat direproduksi.

Jangan menulis **“penelitian pertama”** sebelum dilakukan pencarian literatur terakhir menjelang submission.

---

## 6. Teori Dasar

Landasan teori sebaiknya disusun dari konsep umum menuju implementasi penelitian:

```text
Resource-Aware Systems
        ↓
Resource Sharing under Capacity Constraints
        ↓
Context / Situation-Aware Resource Allocation
        ↓
Dynamic Resource Allocation
        ↓
Pareto / Multi-Objective Optimization
        ↓
QoS-Aware Resource Management
        ↓
Asynchronous Federated Learning
        ↓
Demand Estimation
        ↓
Adaptive Participation + Update Budget
        ↓
Network Intrusion Detection
```

### Konsep yang dipakai

| Konsep | Peran pada penelitian |
|---|---|
| Resource awareness | state klien diamati sebelum resource action dipilih |
| Resource sharing & capacity constraints | communication opportunity dan update budget diperlakukan sebagai resource terbatas |
| Context-aware allocation | latency, throughput, training time, staleness, dan recency menjadi konteks keputusan |
| Dynamic resource allocation | action dapat berubah mengikuti state terbaru setiap klien |
| Pareto efficiency | komunikasi minimum tidak boleh dicapai dengan mengorbankan kualitas model secara berlebihan |
| QoS-aware management | Macro-F1, attack recall, dan AUPRC menjadi quality guardrail |
| Fair resource sharing | mencegah fast-client domination dan starvation |
| Risk-aware scheduling | staleness dan latency dapat dipandang sebagai sinyal risiko update terlambat |

Fairness dan risk-aware scheduling adalah teori pendukung, bukan RQ utama.

---

## 7. Pertanyaan Penelitian

### RQ utama

**RQ1. Bagaimana karakteristik workload dan kondisi klien dapat digunakan untuk membentuk demand yang mengatur participation priority/frequency dan update budget pada Asynchronous Federated Learning untuk NIDS?**

### Sub-RQ

**RQ2.** Sejauh mana *demand-aware joint allocation* mengurangi total komunikasi dan *time-to-target* dibandingkan Async-Uniform pada data non-IID tanpa menurunkan performa deteksi secara bermakna?

**RQ3.** Berapa kontribusi masing-masing actuator, yaitu demand-aware participation dan demand-aware update budgeting, terhadap keuntungan metode gabungan?

**RQ4.** Bagaimana tingkat non-IID, latency, throughput, dan staleness memengaruhi action yang dipilih, communication cost, convergence, dan kualitas deteksi?

**RQ5 — perluasan artikel.** Apakah pola keuntungan yang sama masih terlihat ketika protokol diterapkan secara terpisah pada ROAD atau small-cluster testbed?

RQ5 **bukan syarat penyelesaian penelitian satu bulan**.

---

## 8. Hipotesis

| ID | Hipotesis | Target awal |
|---|---|---|
| H1 | Joint demand-aware policy lebih communication-efficient daripada Async-Uniform | total upload+download bytes untuk mencapai target Macro-F1 turun minimal 15% |
| H2 | Joint policy tidak memperburuk time-to-target secara praktis | degradasi tidak lebih dari 10%; diharapkan membaik pada heterogeneity tinggi |
| H3 | Kualitas model tetap non-inferior terhadap baseline | lower 95% CI selisih final Macro-F1 B3−B0 > −1 percentage point |
| H4 | Joint policy memberi trade-off lebih baik daripada single actuator | Pareto trade-off B3 lebih baik daripada minimal salah satu B1/B2 pada kondisi utama |
| H5 | Manfaat demand-aware meningkat ketika system/network heterogeneity meningkat | analisis interaksi sebagai hasil sekunder |

Target 15%, 10%, dan 1 percentage point adalah **batas praktis pra-eksperimen**, bukan hasil yang diasumsikan. Penelitian tetap selesai secara ilmiah bila hipotesis tidak didukung, selama protokol, pengukuran, dan kontrol eksperimennya valid.

---

## 9. Dataset

### Dataset utama — UNSW-NB15

Eksperimen utama menggunakan **UNSW-NB15** untuk binary intrusion detection:

```text
normal vs attack
```

Aturan data:

- gunakan split resmi;
- encoder dan scaler hanya di-*fit* pada training split;
- official test set tidak boleh dipakai untuk local training, demand calibration, threshold tuning, atau action tuning;
- client partition dibuat setelah preprocessing dibekukan;
- seluruh B0–B3 memakai partition dan seed yang sama;
- simpan feature list, label mapping, data hash, dan partition manifest.

### Dataset eksternal — ROAD

ROAD hanya digunakan setelah main experiment selesai sebagai **cross-dataset replication**.

ROAD tidak:

- digabung dengan UNSW-NB15;
- memakai weights yang sama secara paksa;
- memakai preprocessing UNSW-NB15 tanpa validasi;
- menjadi syarat penelitian satu bulan.

---

## 10. Simulasi Non-IID

Gunakan **Dirichlet label skew**.

Main setting:

```yaml
alpha: 0.5
num_clients: 10
```

Robustness extension:

```text
alpha = 0.1   → severe non-IID
alpha = 0.5   → main condition
alpha = 10    → near-IID control
```

Minimum penelitian:

```text
3 seeds
```

Target artikel:

```text
5 seeds
```

Gunakan istilah **simulated non-IID label skew**, bukan mengklaim bahwa partition tersebut sama dengan distribusi NIDS dunia nyata.

---

## 11. Model NIDS

Gunakan **satu model MLP kecil dan tetap** di seluruh policy.

Contoh:

```text
Input
  ↓
Dense 128
  ↓
ReLU
  ↓
Dropout
  ↓
Dense 64
  ↓
ReLU
  ↓
Output
```

Konfigurasi awal tersedia di `configs/model.yaml`.

Komponen yang harus tetap sama antar-policy:

- architecture;
- initialization seed;
- optimizer;
- learning rate;
- batch size;
- local epoch;
- precision;
- preprocessing.

Penelitian ini **bukan** studi komparasi arsitektur NIDS.

---

## 12. Asynchronous Federated Learning

Dalam protokol utama:

1. klien menerima model global pada versi tertentu;
2. klien melakukan local training;
3. klien mengirim update segera setelah selesai;
4. server tidak menunggu klien lain;
5. update diterapkan ketika tiba;
6. server version bertambah;
7. staleness dihitung dan dicatat;
8. state klien diperbarui.

Jika klien mulai dari `v_start` dan update diterima pada `v_arrival`, maka:

```text
staleness = v_arrival - v_start
```

Semua policy memakai aggregation/staleness rule yang sama.

Synchronous FedAvg boleh digunakan sebagai **reference context** setelah eksperimen utama selesai, tetapi bukan baseline kausal utama.

---

## 13. Client Workload / State Vector

State minimum klien `i` pada waktu `t`:

```text
x_i(t) = [
    n_i,
    T_prev,
    RTT_i,
    BW_i,
    staleness_i,
    age_i
]
```

Dengan:

| Feature | Arti |
|---|---|
| `n_i` | jumlah sampel lokal yang akan dipakai pada local training |
| `T_prev` | waktu local training terakhir |
| `RTT_i` | round-trip latency terkini |
| `BW_i` | throughput/bandwidth terkini |
| `staleness_i` | selisih versi model saat update diterima |
| `age_i` | waktu/server-update events sejak kontribusi terakhir |

Recent contribution score bersifat opsional untuk artikel dan tidak wajib pada main experiment.

---

## 14. Demand Estimation

Demand **tidak dipaksa menjadi satu angka tunggal**.

Satu modul demand menghasilkan:

```text
D_i(t) = [d_part, d_budget]
```

- `d_part` menentukan kebutuhan/kelayakan untuk mendapatkan participation opportunity lebih cepat;
- `d_budget` menentukan besar model update yang layak dikirim.

Alur minimum:

```text
client state
    ↓
normalization dari calibration runs
    ↓
demand estimator
    ├── d_part
    └── d_budget
    ↓
low / medium / high action
```

Implementasi bulan pertama sebaiknya berupa **transparent normalized scoring function**, bukan reinforcement learning.

Aturan penting:

- normalisasi berasal dari calibration run;
- threshold low/medium/high dibekukan sebelum main run;
- final test result tidak boleh digunakan untuk mengubah formula demand;
- mapping state → demand → action harus dapat direproduksi.

---

## 15. Actuator 1 — Participation Priority / Frequency

Pada Asynchronous FL, participation frequency **bukan** “jumlah klien per round”.

Gunakan mekanisme eligibility/cooldown berbasis server-update events.

Grid awal:

| Level | Aturan awal |
|---|---|
| low | cooldown 3 server-update events |
| medium | cooldown 1 server-update event |
| high | eligible segera / priority tinggi |

Demand tinggi dapat:

- mempersingkat cooldown;
- menaikkan dispatch priority.

Demand rendah dapat:

- memperpanjang cooldown;
- menurunkan priority.

Tetap gunakan **maximum inactivity window** agar tidak terjadi starvation.

---

## 16. Actuator 2 — Update Budget

Update budget adalah batas maksimum informasi model yang dikirim dalam satu kontribusi.

Grid utama:

```text
25% model delta
50% model delta
100% model delta
```

Operator awal yang disarankan:

```text
magnitude top-k pada model delta
```

Catatan penting:

- jangan menyebut 25% tensor sebagai 75% communication saving tanpa menghitung bytes aktual;
- transmitted bytes harus memasukkan values, indices, header, metadata, dan overhead relevan;
- compression/serialization time harus dicatat;
- bila memakai error feedback, implementasinya harus identik di semua policy yang memakai sparsification.

---

## 17. Action Space

Dua actuator menghasilkan action:

```text
a_i(t) = [participation_level, update_budget]
```

Dengan grid:

```text
Participation: low | medium | high
Update Budget: 25% | 50% | 100%
```

Sehingga terdapat sembilan pasangan action potensial.

Baseline tidak memilih action adaptif. Proposed method memilih action berdasarkan `D_i(t)`.

Threshold dan action grid **tidak boleh diubah setelah main result dilihat**.

---

## 18. Baseline dan Ablation

| Policy | Participation | Update Budget | Peran |
|---|---|---|---|
| B0 — Async-Uniform | uniform/fixed | 100% fixed | baseline utama |
| B1 — Async + Demand-Participation | demand-aware | 100% fixed | ablation participation |
| B2 — Async + Demand-Budget | uniform/fixed | demand-aware 25/50/100% | ablation update budget |
| B3 — Async + Joint Demand-Aware | demand-aware | demand-aware | metode usulan |
| B4 — Synchronous FedAvg | round-based | 100% fixed | reference tambahan, opsional |

B1 dan B2 **wajib**. Tanpa keduanya, jika B3 menang dari B0 kita tidak mengetahui apakah manfaat berasal dari participation control, budget control, atau kombinasi keduanya.

---

## 19. Proposed Method

Alur utama:

```text
Client state
    ↓
Demand estimation
    ↓
[d_part, d_budget]
    ↓
┌─────────────────────────────┐
│ Participation Scheduler     │
│ Update-Budget Controller    │
└─────────────────────────────┘
    ↓
Fixed local training
    ↓
Budgeted model update
    ↓
Asynchronous server aggregation
    ↓
Event logging
    ↓
State diperbarui
    ↺
```

Aturan isolasi eksperimen:

```text
TIDAK BOLEH BERUBAH ANTAR B0–B3
--------------------------------
aggregation rule
model architecture
optimizer
learning rate
batch size
local epoch
precision
initialization
preprocessing
data partition
network trace untuk paired comparison
```

Jika salah satu komponen tersebut ikut berubah, peningkatan tidak lagi dapat diatribusikan secara bersih pada demand-aware allocation.

---

## 20. Testbed

Minimum testbed:

- Linux host / Linux VM;
- Docker;
- cgroup v2;
- `tc/netem` atau mekanisme setara untuk latency/bandwidth control;
- satu logical server;
- 10 logical clients;
- fixed maximum concurrency, misalnya 3 atau 5 setelah pilot;
- event logger.

### Peran cgroup

Cgroup **bukan actuator adaptif** pada penelitian ini. Cgroup digunakan untuk:

- membuat capability client konsisten;
- atau membentuk client/system heterogeneity yang dapat diputar ulang.

### Network profile

Main experiment menggunakan:

1. `normal`;
2. `heterogeneous`.

Contoh heterogeneous classes:

```text
fast
medium
slow
```

Jangan mengubah non-IID partition saat menguji network heterogeneity. Data heterogeneity dan system/network heterogeneity harus dapat dipisahkan.

---

## 21. Eksperimen

### E0 — Data dan centralized sanity check

Tujuan: memastikan preprocessing dan metrik model benar sebelum masuk Federated Learning.

Kerjakan:

- validasi preprocessing;
- train centralized MLP;
- hitung Macro-F1, attack recall, AUPRC, Accuracy, dan AUROC;
- bekukan official test set.

### E1 — Asynchronous backbone validation

Tujuan: memastikan implementasi async benar.

Kerjakan:

- implementasikan B0 Async-Uniform;
- verifikasi immediate aggregation;
- verifikasi server versioning;
- verifikasi staleness calculation;
- jalankan dua klien dengan speed berbeda;
- pastikan server tidak menunggu klien lambat;
- bekukan aggregation/staleness rule.

### E2 — Communication accounting dan update budget

Tujuan: memastikan update budget benar-benar mengubah bytes.

Kerjakan:

- implementasikan 25/50/100%;
- serialisasi update;
- hitung values, indices, header, metadata;
- uji decompress/apply;
- ukur compression/serialization overhead;
- sanity check dampak budget pada model.

### E3 — Demand calibration

Tujuan: membangun demand rule tanpa test leakage.

Kerjakan:

- rekam `n_i`, train time, RTT, throughput, staleness, age;
- normalisasi menggunakan calibration data;
- tentukan threshold low/medium/high;
- tentukan fairness guardrail;
- bekukan formula dan threshold.

### E4 — Pilot ablation

Tujuan: memastikan policy isolation.

Kerjakan:

- B0–B3 pada satu seed;
- satu network profile;
- pastikan B1 hanya mengubah participation;
- pastikan B2 hanya mengubah update budget;
- pastikan B3 mengubah keduanya;
- perbaiki bug;
- freeze protocol dan analysis plan.

### E5 — Main comparison

Tujuan: menjawab RQ utama.

Kerjakan:

```text
B0, B1, B2, B3
alpha = 0.5
3 seeds minimum
network profile yang sama per paired run
partition yang sama
initialization yang sama
maximum concurrency yang sama
```

Simpan event-level log dan periodic evaluation.

### E6 — Heterogeneity stress

Tujuan: melihat apakah demand-aware allocation makin berguna ketika sistem makin heterogen.

Kerjakan:

- ulang B0–B3 pada heterogeneous latency/throughput profile;
- data partition tetap;
- analisis interaction policy × system heterogeneity.

### E7 — Non-IID robustness

Hanya setelah E5–E6 selesai:

```text
alpha = 0.1
alpha = 10
```

ROAD dan synchronous reference dilakukan terakhir.

---

## 22. Metrik Evaluasi

### A. Communication endpoints — primer

1. total upload bytes;
2. total download bytes;
3. total communicated bytes;
4. bytes-to-target Macro-F1;
5. accepted client updates untuk mencapai target;
6. actual compression ratio setelah index dan metadata dihitung.

### B. System/time endpoints

1. local training time per contribution;
2. network transfer time;
3. serialization/compression overhead;
4. wall-clock time-to-target Macro-F1;
5. mean/median/p95 staleness;
6. participation share per client;
7. maximum inactivity window.

### C. Model endpoints — primer

1. Macro-F1;
2. attack-class recall;
3. AUPRC.

### D. Model/system endpoints — sekunder

- Accuracy;
- AUROC;
- balanced accuracy;
- confusion matrix;
- server validation loss;
- Jain participation fairness index;
- worst-client validation metric bila tersedia.

Accuracy dan AUROC tetap boleh dilaporkan, tetapi tidak boleh menjadi satu-satunya dasar kesimpulan.

---

## 23. Kriteria Keberhasilan

B3 dinilai praktis bila memenuhi seluruh atau sebagian besar criteria yang dipraregistrasikan:

1. total communicated bytes atau bytes-to-target turun minimal **15%** dibanding B0;
2. lower 95% CI selisih Macro-F1 `B3 − B0` berada di atas **−1 percentage point**;
3. time-to-target tidak memburuk lebih dari **10%**;
4. byte saving tetap terlihat setelah index, header, dan metadata dihitung;
5. tidak ada persistent client starvation;
6. B3 memberi trade-off communication-quality lebih baik daripada minimal salah satu B1/B2.

Kegagalan hipotesis tetap merupakan hasil penelitian.

Contoh interpretasi:

```text
Bytes turun 25%
Macro-F1 turun 4 percentage points
→ komunikasi memang turun, tetapi proposed TIDAK lolos quality guardrail.
```

```text
Tensor density turun 50%
Serialized bytes hanya turun 5%
→ klaim communication saving harus memakai 5%, bukan 50%.
```

---

## 24. Analisis Statistik

Gunakan **paired comparison** karena seed, partition, initialization, dan network profile sama antar-policy.

Minimum laporan:

- mean;
- median;
- standard deviation;
- raw difference;
- 95% confidence interval;
- effect size yang relevan.

Untuk Macro-F1 gunakan **non-inferiority analysis** dengan margin yang ditetapkan sebelum main run.

Gunakan paired bootstrap pada level **run/seed** untuk:

- communication bytes;
- time-to-target;
- Macro-F1.

Jangan memperlakukan ribuan update event dari satu run sebagai ribuan sampel independen.

Bila banyak uji sekunder dilakukan, gunakan Holm correction.

Visualisasi utama sebaiknya mencakup Pareto frontier antara:

```text
communication bytes
        vs
 time-to-target
        vs
   Macro-F1
```

---

## 25. Failure Analysis

Audit minimal 20 kasus ekstrem/kegagalan dan hubungkan dengan state, demand, action, staleness, byte cost, dan model outcome.

Kategori minimum:

1. **fast-client domination** — klien cepat terlalu sering dipilih;
2. **starvation** — klien lambat terlalu lama tidak berkontribusi;
3. **staleness explosion** — update tiba terlalu tua;
4. **under-budgeting** — budget 25% terlalu agresif dan merusak quality;
5. **over-budgeting** — policy terlalu sering memilih 100%;
6. **metadata overhead** — index/header menghapus keuntungan compression;
7. **demand misclassification** — state noisy membuat action keliru;
8. **network-profile deviation** — kondisi actual tidak sesuai profile;
9. **rare non-IID client suppression** — client dengan distribusi penting jarang mendapat kesempatan;
10. **compression overhead** — waktu kompresi lebih besar daripada transfer saving.

Failure analysis bukan lampiran kosmetik. Ini membantu menjelaskan **kapan** mekanisme demand-aware gagal.

---

## 26. Grafik dan Tabel yang Harus Dihasilkan

1. mapping katalog → adaptasi DSIC-2907;
2. tabel client workload/state dan network profile;
3. distribusi selected participation level dan update budget;
4. cumulative total bytes vs accepted updates;
5. Macro-F1 vs cumulative communicated bytes;
6. Macro-F1 vs wall-clock time;
7. bytes-to-target per policy;
8. time-to-target per policy;
9. staleness distribution per policy;
10. participation share dan starvation audit;
11. ablation B0–B3;
12. Pareto plot communication cost vs Macro-F1;
13. failure matrix: state → demand → action → outcome.

Jangan hanya menampilkan run terbaik. Plot seluruh seed.

---

## 27. Rencana Kerja 1 Bulan

### Minggu 1 — Async backbone dan measurement

**Hari 1–2**

- verifikasi UNSW-NB15;
- preprocessing tanpa leakage;
- centralized baseline;
- Linux/Docker testbed;
- network emulation.

**Hari 3–4**

- implementasikan B0;
- server versioning;
- immediate aggregation;
- staleness logging;
- test dua client speed.

**Hari 5–7**

- byte accounting;
- update budget 25/50/100%;
- freeze model, local epoch, batch size, aggregation rule, concurrency.

**Gate Minggu 1**

```text
[ ] B0 end-to-end berjalan
[ ] actual bytes dapat dihitung
[ ] update budget 25/50/100% valid
[ ] staleness calculation benar
```

### Minggu 2 — Demand estimator dan pilot

**Hari 8–10**

- workload/state monitor;
- calibration run;
- feature normalization;
- demand module;
- participation scheduler.

**Hari 11–12**

- B1/B2/B3;
- fairness guardrail;
- test policy isolation;
- cek local compute dan aggregation identik.

**Hari 13–14**

- pilot B0–B3 satu seed;
- perbaiki bug;
- freeze threshold;
- freeze action grid;
- freeze target Macro-F1;
- freeze analysis plan.

**Gate Minggu 2**

```text
[ ] B1 hanya mengubah participation
[ ] B2 hanya mengubah budget
[ ] B3 mengubah keduanya
[ ] tidak ada starvation tak terkendali
[ ] accounting stabil
[ ] evaluation stabil
```

### Minggu 3 — Main experiment

**Hari 15–18**

- B0–B3;
- alpha 0.5;
- tiga seed;
- event-level logging;
- periodic metrics;
- checkpoint.

**Hari 19–21**

- heterogeneous profile;
- ulang hanya technical failure dengan reason log;
- mulai robustness alpha bila main run lengkap.

**Output Minggu 3**

```text
B0–B3 lengkap
bytes lengkap
time lengkap
staleness lengkap
participation lengkap
model metrics lengkap
```

### Minggu 4 — Analisis dan penulisan

**Hari 22–24**

- bytes-to-target;
- time-to-target;
- CI;
- non-inferiority;
- cumulative curves;
- Pareto plot;
- audit actual serialized bytes.

**Hari 25–26**

- ablation;
- failure analysis;
- alpha robustness bila waktu cukup;
- ROAD hanya jika semua main analysis lengkap.

**Hari 27–28**

- Method;
- Results;
- Discussion;
- Threats to Validity;
- artifact documentation.

**Hari 29–30**

- fresh reproduction satu tabel/plot utama;
- freeze code/config/data manifest/results;
- materi sidang;
- draft artikel v0.8.

---

## 28. Tools Penelitian

### Core software

- Python 3.11+;
- PyTorch;
- NumPy;
- pandas;
- scikit-learn;
- SciPy;
- matplotlib;
- PyYAML.

### Federated-learning implementation

Implementasi dapat dibuat secara ringan sendiri di atas Python/PyTorch agar server version, staleness, event timing, byte accounting, dan policy isolation mudah diaudit.

Framework FL eksternal boleh digunakan bila tidak menghalangi pencatatan event-level dan tidak mengubah definisi eksperimen.

### Testbed

- Ubuntu/Linux;
- Docker;
- cgroup v2;
- `tc/netem` untuk latency/bandwidth emulation.

### Reproducibility

- Git;
- YAML configuration;
- fixed seeds;
- manifest data;
- partition manifest;
- checksum/hash;
- event logs;
- pytest.

### Statistik

- NumPy/pandas;
- SciPy;
- bootstrap custom yang terdokumentasi;
- statsmodels bila diperlukan.

---

## 29. Struktur Repositori

```text
DSIC-2907/
└── demand-aware-async-fl-nids/
    ├── README.md
    ├── pyproject.toml
    ├── .gitignore
    │
    ├── configs/
    │   ├── model.yaml
    │   ├── async_fl.yaml
    │   ├── demand.yaml
    │   ├── network_profiles.yaml
    │   └── experiments.yaml
    │
    ├── data/
    │   ├── manifests/
    │   │   └── README.md
    │   └── partitions/
    │       └── README.md
    │
    ├── src/
    │   ├── preprocess.py
    │   ├── partition.py
    │   ├── async_server.py
    │   ├── client.py
    │   ├── demand.py
    │   ├── scheduler.py
    │   ├── update_budget.py
    │   ├── compressor.py
    │   ├── monitor.py
    │   └── analyze.py
    │
    ├── tests/
    │   ├── test_async_apply.py
    │   ├── test_staleness.py
    │   ├── test_byte_accounting.py
    │   ├── test_budget_operator.py
    │   ├── test_scheduler_fairness.py
    │   └── test_policy_isolation.py
    │
    ├── results/
    │   ├── raw/
    │   ├── processed/
    │   └── figures/
    │
    └── paper/
        └── manuscript.md
```

---

## 30. Peran Setiap File

### `configs/model.yaml`

Membekukan arsitektur MLP dan local training hyperparameters.

### `configs/async_fl.yaml`

Membekukan:

- jumlah clients;
- concurrency;
- aggregation rule;
- staleness handling;
- evaluation interval;
- non-IID settings.

### `configs/demand.yaml`

Mendefinisikan:

- workload/state features;
- normalization;
- `d_part` dan `d_budget`;
- participation levels;
- update budget levels;
- fairness guardrail.

### `configs/network_profiles.yaml`

Menyimpan network profile yang dapat diputar ulang untuk paired comparison.

### `configs/experiments.yaml`

Mendefinisikan B0–B3, seed, alpha, dan network profile.

### `src/preprocess.py`

Preprocessing UNSW-NB15 tanpa leakage.

### `src/partition.py`

Membangun dan menyimpan Dirichlet non-IID partition.

### `src/async_server.py`

Server versioning, immediate apply, staleness-aware aggregation, checkpoint.

### `src/client.py`

Local training client dengan model/training rule tetap.

### `src/demand.py`

State normalization dan demand estimation.

### `src/scheduler.py`

Participation eligibility, priority, cooldown, fairness floor.

### `src/update_budget.py`

Memilih 25/50/100% update budget.

### `src/compressor.py`

Implementasi operator budget/sparsification dan actual serialized byte accounting.

### `src/monitor.py`

Merekam event-level state, timing, action, staleness, dan communication bytes.

### `src/analyze.py`

Membentuk tabel, metrik, CI, curves, dan failure analysis.

---

## 31. Minimum Event Log

Setiap accepted atau attempted contribution minimal menyimpan:

```json
{
  "run_id": "...",
  "seed": 42,
  "server_version": 137,
  "client_id": 3,
  "model_start_version": 131,
  "staleness": 6,
  "num_samples": 14321,
  "local_train_sec": 17.8,
  "rtt_ms": 84.0,
  "throughput_mbps": 18.2,
  "time_since_last_update": 29.4,
  "demand_part": 0.72,
  "demand_budget": 0.61,
  "participation_level": "high",
  "update_budget": 0.50,
  "upload_bytes": 263488,
  "download_bytes": 510224,
  "serialization_sec": 0.021,
  "transfer_sec": 0.114,
  "accepted": true
}
```

Tambahkan field lain bila dibutuhkan, tetapi jangan menghapus field yang diperlukan untuk menjawab RQ.

---

## 32. Reproducibility Rules

Setiap main run harus memiliki:

```text
run_id
seed
config snapshot
model config
FL config
demand config
network profile
partition manifest
data hash
code commit hash
raw event log
periodic model metrics
failure reason bila run gagal
```

Main result tidak boleh diubah dengan:

- mengganti threshold setelah melihat test result;
- memilih hanya seed terbaik;
- membuang failed run tanpa reason log;
- memakai partition berbeda untuk policy yang dibandingkan;
- mengubah network trace agar suatu policy terlihat lebih baik.

---

## 33. Ancaman terhadap Validitas

### Internal validity

B0–B3 harus memakai aggregation, concurrency, model, local epoch, batch size, optimizer, precision, partition, dan paired network profile yang sama.

### Construct validity

Jangan mencampurkan:

```text
communication bytes
network transfer time
serialization time
local training time
wall-clock time
```

Semua konstruk tersebut berbeda.

### Demand validity

Demand adalah konstruk penelitian. Karena itu feature, normalization, threshold, dan mapping action wajib dibekukan setelah calibration.

### Statistical validity

Update event dari satu run saling berkorelasi. Unit inferensi utama adalah run/seed, bukan ribuan event individual.

### Data validity

Dirichlet partition adalah simulated label skew.

### System validity

Network emulator dan co-located containers bukan real edge deployment.

### External validity

Kesimpulan utama berasal dari UNSW-NB15. ROAD atau small-cluster validation diperlukan bila ingin memperkuat generalisasi untuk artikel.

### Novelty validity

Jangan klaim “first” tanpa final literature search pada:

- demand-aware asynchronous scheduling;
- adaptive update budget;
- communication-efficient asynchronous FL;
- joint resource control.

---

## 34. Quality Gate — Penelitian Selesai

Minimal seluruh item berikut terpenuhi:

```text
[ ] B0 berjalan end-to-end
[ ] immediate async aggregation terverifikasi
[ ] server versioning terverifikasi
[ ] staleness calculation terverifikasi
[ ] demand module menghasilkan d_part dan d_budget
[ ] B0–B3 selesai minimal 3 seeds
[ ] partition dan network profile sama untuk paired comparison
[ ] update budget 25/50/100% menghasilkan byte accounting aktual
[ ] non-IID alpha dan seed terdokumentasi
[ ] total bytes dihitung
[ ] bytes-to-target dihitung
[ ] time-to-target dihitung
[ ] staleness dihitung
[ ] participation share dihitung
[ ] Macro-F1 dihitung
[ ] attack recall dihitung
[ ] AUPRC dihitung
[ ] B1/B2 ablation tersedia
[ ] non-inferiority Macro-F1 dilaporkan dengan CI
[ ] starvation audit dilakukan
[ ] failure analysis tersedia
[ ] satu command mereproduksi minimal satu tabel/plot utama
[ ] klaim dibatasi pada controlled async FL-NIDS + simulated non-IID
```

---

## 35. Quality Gate — Submit Artikel

Tambahan di atas quality gate penelitian:

```text
[ ] 5 seeds
[ ] alpha 0.1, 0.5, 10
[ ] normal + heterogeneous network profiles
[ ] feature ablation demand
[ ] byte accounting termasuk metadata dan compression overhead
[ ] ROAD cross-dataset replication atau small-cluster validation
[ ] final literature search joint participation + update budget
[ ] artifact dapat dijalankan pembaca lain
[ ] title/abstract tidak mengklaim async atau sparsification sebagai novelty
[ ] seluruh communication reduction didukung byte-level evidence
```

---

## 36. Yang Tidak Dikerjakan pada Bulan Pertama

- adaptive local epoch;
- adaptive batch size;
- adaptive CPU-memory allocation;
- reinforcement learning scheduler;
- algoritma compression baru;
- differential privacy;
- secure aggregation;
- poisoning/adversarial defense;
- multi-model NIDS comparison;
- lebih dari dua dataset;
- real edge deployment;
- dashboard produksi.

Komponen di atas bukan salah. Masalahnya adalah menambahkan semuanya sebelum B0–B3 selesai akan membuat kontribusi utama sulit diisolasi dan penelitian satu bulan berisiko tidak selesai.

---

## 37. Instalasi Awal

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
pytest -q
```

Jika pada Ubuntu paket `venv` belum tersedia:

```bash
sudo apt update
sudo apt install python3-venv
```

---

## 38. Urutan Implementasi yang Disarankan

Jangan mulai dari demand estimator.

Urutan yang lebih aman:

```text
1. preprocessing
2. centralized model
3. async B0
4. server versioning
5. staleness
6. byte accounting
7. update budget
8. workload monitor
9. demand estimation
10. participation scheduler
11. B1 / B2 / B3
12. main experiment
13. statistics
14. article
```

Jika B0 belum benar, jangan lanjut membuat B3.

---

## 39. Catatan Pembimbing

Alur besarnya kira-kira seperti ini:

```text
UNSW-NB15
   ↓
preprocessing tanpa leakage
   ↓
partition ke 10 klien
Dirichlet non-IID alpha = 0.5
   ↓
jalankan Asynchronous FL
   ↓
setiap klien menghasilkan state
n_i | train time | RTT | bandwidth | staleness | age
   ↓
demand estimation
   ↓
D_i(t) = [d_part, d_budget]
   ↓
┌───────────────────────────────┐
│ participation priority        │
│ update budget 25/50/100%      │
└───────────────────────────────┘
   ↓
local training yang SAMA
   ↓
model update dikompresi sesuai budget
   ↓
hitung serialized bytes aktual
   ↓
server langsung menerima + apply update
   ↓
update staleness dan client state
   ↺
   ↓
bandingkan B0 | B1 | B2 | B3
   ↓
ukur bytes-to-target, time-to-target,
staleness, fairness, Macro-F1, recall, AUPRC
   ↓
heterogeneity stress
   ↓
non-inferiority + Pareto + failure analysis
```

Secara eksperimen bisa seperti berikut.

1. **Mulai dari membangun baseline NIDS dan data partition, bukan langsung membuat demand-aware policy.** Gunakan UNSW-NB15 sebagai dataset utama dan selesaikan preprocessing secara terpusat terlebih dahulu. Encoder dan scaler hanya boleh belajar dari training split. Setelah centralized MLP memberi hasil yang masuk akal, training data dibagi menjadi 10 logical clients menggunakan Dirichlet label skew dengan `alpha = 0.5`. Simpan partition manifest supaya B0, B1, B2, dan B3 benar-benar melihat distribusi data klien yang sama.

   Gambaran sederhananya:

```text
UNSW-NB15 training split
          ↓
preprocessing fit pada train saja
          ↓
Dirichlet partition alpha = 0.5
          ↓
client 0
client 1
client 2
...
client 9
```

   Jadi eksperimen ini bukan bertanya **“model NIDS apa yang paling akurat?”**. Modelnya sengaja dibuat tetap. Pertanyaan kita adalah apa yang terjadi pada biaya komunikasi dan convergence ketika cara memberikan kesempatan kontribusi serta besar update diubah berdasarkan kondisi klien.

2. **Bangun Asynchronous FL baseline yang benar sebelum menambahkan mekanisme demand.** Baseline B0 adalah Async-Uniform. Setiap klien memakai eligibility/participation rule yang sama dan mengirim 100% model delta. Ketika satu klien selesai local training, update dikirim dan langsung diterapkan server tanpa menunggu klien lain. Server version harus naik setiap accepted update.

   Misalnya:

```text
Server global model v=20

Client A mulai dari v=20 ---- selesai cepat ----> update A tiba
                                                server apply
                                                global v=21

Client B mulai dari v=20 ------------------------------ selesai
                                                        update B tiba
                                                        server sekarang v=21
                                                        staleness B = 1
                                                        server apply
                                                        global v=22
```

   Kalau implementasi masih menunggu A dan B selesai bersama, itu bukan asynchronous backbone yang kita perlukan. E1 belum lolos dan eksperimen berikutnya jangan dijalankan.

3. **Setelah asynchronous backbone benar, baru ukur communication cost dengan benar.** Update budget adalah bagian penting penelitian, sehingga penghematan komunikasi tidak boleh dihitung hanya dari persentase parameter yang dipertahankan. Misalnya top-k mempertahankan 25% nilai model delta, sistem tetap perlu mengirim indices dan metadata. Karena itu hitung ukuran data setelah serialisasi.

   Misalnya:

```text
model delta penuh
      ↓
top-k 25%
      ↓
values
indices
header
metadata
      ↓
serialize
      ↓
ACTUAL BYTES
```

   Angka `25% update budget` **tidak berarti** otomatis `75% communication saving`. Klaim penelitian harus menggunakan actual upload/download bytes.

4. **Baru setelah baseline dan byte accounting stabil, bentuk client state dan demand.** Setiap klien mempunyai kondisi yang berubah seiring waktu. State minimum yang kita gunakan adalah jumlah sampel lokal, waktu local training terakhir, RTT, throughput, staleness, dan age sejak kontribusi terakhir.

```text
client i
   ↓
[n_i,
 T_prev,
 RTT_i,
 BW_i,
 staleness_i,
 age_i]
   ↓
demand estimator
   ↓
[d_part, d_budget]
```

   Kita sengaja tidak memaksa seluruh kondisi tersebut menjadi satu angka yang maknanya kabur. Satu modul boleh menerima feature set yang sama, tetapi mempunyai dua output karena participation dan update budget adalah dua keputusan yang berbeda.

   Untuk penelitian satu bulan, demand estimator tidak perlu berupa neural network atau reinforcement learning. Scoring function yang transparan dan dapat diaudit justru lebih baik. Yang penting normalization, threshold, dan mapping action ditentukan dari calibration run lalu **dibekukan sebelum main experiment**.

5. **Demand kemudian mengontrol dua actuator yang berbeda.** `d_part` mengatur seberapa cepat klien kembali eligible atau seberapa tinggi prioritas dispatch-nya. `d_budget` menentukan apakah klien mengirim 25%, 50%, atau 100% model delta. Local training tetap sama.

```text
d_part
  ↓
low    → cooldown 3 events
medium → cooldown 1 event
high   → eligible segera


d_budget
  ↓
low    → 25%
medium → 50%
high   → 100%
```

   Perlu **fairness floor**. Klien cepat atau berbandwidth tinggi tidak boleh terus-menerus mendapat kesempatan sampai klien lambat hilang dari training. Ini sangat penting pada non-IID karena client yang jarang dipilih mungkin membawa pola attack yang tidak dominan pada client lain.

6. **Main experiment bukan sekadar B0 lawan B3.** Kita wajib menjalankan empat policy supaya mekanisme yang memberi keuntungan dapat dipisahkan.

```text
B0 = Async-Uniform
     participation fixed
     budget 100%

B1 = Demand-Participation
     participation adaptive
     budget 100%

B2 = Demand-Budget
     participation fixed
     budget adaptive

B3 = Joint Demand-Aware
     participation adaptive
     budget adaptive
```

   Jika hasilnya misalnya:

```text
B0 bytes-to-target = 900 MB
B1 bytes-to-target = 850 MB
B2 bytes-to-target = 650 MB
B3 bytes-to-target = 620 MB
```

   maka kita dapat melihat bahwa penghematan terbesar mungkin berasal dari budget control, sementara participation memberi tambahan kecil. Tanpa B1 dan B2, kita hanya tahu B3 menang tetapi tidak tahu **mengapa**.

7. **Ukuran kemenangan penelitian bukan Accuracy tertinggi.** Endpoint utama sistem adalah communication bytes dan time-to-target, sedangkan kualitas NIDS menjadi guardrail. Gunakan Macro-F1, attack recall, dan AUPRC sebagai metrik model utama.

   Logikanya:

```text
                lebih hemat komunikasi
                        ↑
                        |
                        |
     quality jatuh      |      target penelitian
     terlalu jauh       |      ↓
------------------------+----------------------→ model quality
                        |
```

   Misalnya B3 menghemat 30% bytes tetapi Macro-F1 turun 5 percentage points. Itu **bukan kemenangan**. Sebaliknya, jika bytes-to-target turun 20%, Macro-F1 tetap dalam margin non-inferiority, dan tidak terjadi starvation, maka kita punya bukti yang jauh lebih kuat bahwa demand-aware allocation memang berguna.

8. **Sesudah main comparison, uji kondisi heterogen.** Network profile normal belum tentu cukup untuk menunjukkan manfaat policy adaptif. Karena itu B0–B3 diulang pada profile yang mempunyai fast, medium, dan slow clients. Yang harus tetap adalah data partition; yang berubah hanya system/network profile.

```text
client fast   → RTT rendah, bandwidth tinggi
client medium → RTT sedang, bandwidth sedang
client slow   → RTT tinggi, bandwidth rendah
```

   Pertanyaan sekundernya: **apakah keuntungan B3 makin besar ketika heterogeneity meningkat?** Bila tidak, itu juga hasil penting karena berarti demand-aware mechanism mungkin tidak memberi manfaat di luar overheadnya.

9. **Terakhir lakukan non-inferiority, Pareto analysis, dan failure analysis.** Jangan hanya mengambil rata-rata tiga seed dan menyatakan metode unggul. Plot seluruh seed, hitung confidence interval, lakukan paired comparison, dan baca trade-off komunikasi–waktu–quality. Audit juga minimal 20 failure cases: client starvation, stale update, under-budgeting, over-budgeting, metadata overhead, atau demand misclassification.

   Hasil penelitian yang kuat bukan kalimat:

   > “Metode B3 memiliki accuracy tertinggi.”

   tetapi lebih seperti:

   > “Joint demand-aware participation and update budgeting mengurangi bytes-to-target dibanding Async-Uniform pada backbone asynchronous yang sama, sementara Macro-F1 tetap berada dalam margin non-inferiority; keuntungan terbesar muncul pada network heterogeneity tinggi, tetapi policy mengalami failure mode berupa under-budgeting pada client dengan distribusi attack langka.”

   Kalimat seperti itu menjawab **mekanisme, trade-off, kondisi keberhasilan, dan kondisi kegagalan** sekaligus.

Untuk tools-nya, penelitian ini cukup dikerjakan dengan **Python + PyTorch** untuk model dan Federated Learning logic, `NumPy/pandas/scikit-learn/SciPy` untuk preprocessing dan evaluasi, serta `matplotlib` untuk visualisasi. Linux dan Docker dipakai untuk testbed; `cgroup v2` membantu membuat capability client konsisten, sedangkan `tc/netem` digunakan untuk latency/bandwidth emulation. Seluruh konfigurasi eksperimen disimpan dalam YAML, partition dan dataset diberi manifest/hash, dan setiap run menyimpan event-level log. Tidak perlu Kubernetes, Spark, Hadoop, reinforcement learning, atau edge device fisik untuk menjawab RQ utama bulan pertama.

Yang paling penting: penelitian ini bukan pertanyaan **“apakah asynchronous FL lebih bagus daripada synchronous FL?”**, dan bukan pula **“apakah sparsification mengurangi komunikasi?”**. Pertanyaan utamanya adalah **“apakah state klien dapat diubah menjadi demand yang secara bersama mengatur kesempatan partisipasi dan update budget sehingga Asynchronous FL mencapai kualitas NIDS yang sama dengan komunikasi lebih sedikit, dan pada kondisi apa keuntungan itu muncul atau gagal?”** Itulah inti eksperimennya.

