BEI FINANCIAL STATEMENTS DASHBOARD V2.2 — PERIOD MATRIX
=====================================================
Tujuan: menampilkan Financial Statements dalam matriks historis, terbaru di kanan.
Semua angka tetap RAW/REVIEW sampai verifikasi satuan/konteks/PDF selesai.

CARA INSTAL
1. Extract ZIP ke C:\Analisis_Saham_BEI\BEI_Dashboard_V2_2
2. Pertahankan database: C:\Analisis_Saham_BEI\BEI_Master_Output\BEI_Financial_Master.db
3. Buka CMD dan jalankan:
     cd /d C:\Analisis_Saham_BEI\BEI_Dashboard_V2_2
     py dashboard_v2.pyw
   Alternatif jika launcher .pyw tidak berjalan:
     py -c "import runpy; runpy.run_path('dashboard_v2.pyw',run_name='__main__')"
4. Jika database tidak ditemukan, klik 'Pilih Database'.

PILIHAN MODE
- Annual: laba rugi dan arus kas FULL YEAR saja; saldo Desember dari pembanding
  neraca interim ditampilkan sebagai 31 Dec YYYY (BS only), bukan FY laba rugi.
- Quarterly + YTD (kumulatif): 3M,6M,9M dari pelaporan interim; untuk Neraca
  tanggal akhir kuartal. Tampilan Q3 tidak berarti laba rugi Q3 standalone.
- Quarterly + Standalone: sengaja DIBLOKIR; masih harus memverifikasi
  penyeragaman satuan, tanggal periode, ruang lingkup konsolidasi antar filing.
- All Periods: seluruh FY, YTD, dan snapshot neraca yang terpetakan, kronologis.

STATUS KOSONG
- 'N/A': akun tidak berlaku untuk kolom BS-only.
- 'Belum ada': angka tidak ditemukan atau konteks belum dipetakan. BUKAN nol.
- 'REVIEW' (ditampilkan pada detail): angka mentah tersedia, belum boleh dipakai
  untuk valuasi atau konten publik tanpa verifikasi.
Klik sel untuk nama file sumber, worksheet, sel, currency, skala penyajian.

PERHATIAN
- Data dari kolom pembanding tahunan/kuartalan dipetakan ke tahun fiskal masing-masing.
- Nilai mentah dari file berbeda dapat menggunakan skala dan mata uang berbeda.
- Program READ ONLY, tidak mengubah DB lama, Excel, atau PDF.
- Hasil CSV tersimpan di C:\Analisis_Saham_BEI\BEI_Dashboard_Output\<TICKER>.
- Program tidak membutuhkan pip tambahan; Tkinter dari Python Windows.
- Smart App Control: jangan nonaktifkan perlindungan Windows untuk menjalankannya.
