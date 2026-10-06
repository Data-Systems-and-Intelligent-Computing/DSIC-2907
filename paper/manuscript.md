# Manuscript Draft — DSIC-2907

## Working Title
Demand-Aware Adaptive Participation and Update Budgeting for Communication-Efficient Asynchronous Federated Network Intrusion Detection under Non-IID Data

## Sections
1. Introduction
2. Related Work
3. Problem Formulation
4. Demand-Aware Policy
5. Experimental Design
6. Results
7. Ablation and Failure Analysis
8. Threats to Validity
9. Conclusion

## Research Positioning In The Same Domain
Penelitian ini adalah sebuah evaluasi terkontrol mengenai joint runtime-state-driven participation dan update-budget control untuk Federated NIDS asinkron pada data non-IID yang tersimulasikan, dengan atribusi peningkatan eksplisit untuk tiap aktuator dan byte-level communication accounting. Hal yang perlu ditekankan adalah kejelasan demand-estimation (state -> `[d_part, d_budget]`) dan desain B0-B3 daripada metode agregasi terbaru, selection, atau algoritma kompresi.

## Final Contribution
1. Problem framing
    - Penelitian ini mempelajari bagaimana cara memetakan observable client runtime/workload state menjadi dua keputusan dalam hal communication (participation priority dan per-client update budget) pada backbone AFL untuk NIDS yang telah ditetapkan.

2. Design contribution
    - Sebuah antarmuka mengenai demand-estimation yang menggunakan state vektor minimum `[n_i, T_prev, RTT_i, BW_i, staleness_i, age_i]` dan menghasilkan `d_part` serta `d_budget`, diimplementasikan sebagai sebuah deterministic scoring function yang transparan.

3. Experimental contribution
    - Sebuah ablasi dengan empat peraturan (B0-B3) yang mengisolasikan efek dari participation control, update budgeting, dan kombinasi dari keduanya pada partisi UNSW-NB15 yang bersifat non-IID, dengan byte-level communication metrics serta batasan Macro-F1 yang tidak menurun dan time-to-target.

4. Empirical findings
    - trade-off yang terkuantifikasi antara total communicated bytes, bytes-to-target, time-to-target, staleness, participation fairness, dan performa NIDS, sehingga menampilkan apakah joint control menghasilkan communication-quality frontier yang baik secara jelas dibandingkan single-actuator policies.