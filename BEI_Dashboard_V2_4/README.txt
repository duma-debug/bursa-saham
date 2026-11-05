BEI DASHBOARD V2.4 — PEMULIHAN DATA FY2021 DARI LAPORAN 2022
==============================================================

TUJUAN
Memunculkan FY2021 dari kolom pembanding FY2022, dengan tahun terbaru
selalu di sebelah kanan. Tidak memaksakan angka 2021 dari laporan 2022
menjadi nilai FY2022 dan tidak melakukan perhitungan valuasi.

PERSIAPAN
1. Ekstrak seluruh berkas ZIP ke:
   C:\Analisis_Saham_BEI\BEI_Dashboard_V2_4
2. Pastikan dua database ini masih ada:
   C:\Analisis_Saham_BEI\financial_production.db
   C:\Analisis_Saham_BEI\BEI_Master_Output\BEI_Financial_Master.db
3. File Excel TIDAK perlu dipindah maupun diimpor ulang.

CARA CEPAT — TIDAK PERLU PERINTAH PEMULIHAN TERPISAH
1. Buka CMD:
   cd /d C:\Analisis_Saham_BEI\BEI_Dashboard_V2_4
   py dashboard_v2.pyw
2. Klik tombol 'Pulihkan FY2021', lalu setujui pembuatan backup.
3. Pilih AALI > Annual > All, lalu 'Analisis / Refresh'.
4. Kolom FY2021 sekarang muncul di paling kiri; FY2025 di paling kanan.

ALTERNATIF — PEMULIHAN LANGSUNG LEWAT CMD
   py restore_comparatives.py --base "C:\Analisis_Saham_BEI"

HASIL
- Tabel tambahan 'legacy_xbrl_facts' dalam database master
- Backup: BEI_Financial_Master.db.before_v24.bak
- Laporan: BEI_Master_Output\legacy_2022_recovery_report.json
- Tidak mengubah database financial_production.db, file Excel, atau PDF.

CARA BEKERJA
- Mengambil sheet XBRL 2022 dalam database staging, kolom B=2022,
  C=2021, dengan label akun Inggris dari kolom D.
- Membaca tanggal dari metadata worksheet 1000000.
- Hanya menggunakan label akun yang cocok secara eksplisit.
- Simpan sumber worksheet/sel, berkas dan context per fakta.
- Jika ada beberapa versi tahun yang sama, dashboard tetap memilih salah
  satunya secara konservatif dan alternatif bisa diperiksa.
- Mode Annual menggunakan periode penuh untuk laba rugi/arus kas,
  sementara saldo neraca berada pada tanggal akhir periode.

BATASAN DAN PERINGATAN
- Pemulihan berjalan untuk 19 berkas 2022 dengan template yang sudah
  dipetakan; bank, asuransi, dan perusahaan pembiayaan tidak dipaksakan
  masuk menggunakan mapping nonbank. Lihat laporan JSON.
- Semua angka adalah NILAI MENTAH dalam satuan yang dilaporkan sumber.
  Besaran 2021-2022 mungkin berbeda skala dari 2023-2025; jangan
  menginterpretasikan penurunan/kenaikan antarfile secara langsung.
- Status REVIEW: belum layak untuk konten publik, forecasting, atau valuasi.
- Tidak ada fungsi hapus file sumber. Backup tetap harus dipertahankan.
- Memerlukan Python dan Tkinter bawaan Python pada Windows.
