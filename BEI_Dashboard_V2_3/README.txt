INVESTOR MANDIRI — BEI Financial Statements Dashboard V2.3
PERBAIKAN CASH FLOW FY & METADATA PERIODE

INSTALASI WINDOWS
1. Extract ZIP ke C:\Analisis_Saham_BEI\BEI_Dashboard_V2_3
2. Jangan hapus database master lama.
3. Buka CMD (lebih aman daripada double-click bila Windows Smart App Control memblokir .bat).
4. Jalankan:
   cd /d C:\Analisis_Saham_BEI\BEI_Dashboard_V2_3
   py dashboard_v2.pyw
5. Pilih AALI > Annual > Cash Flow (cash_flow).

SUMBER DATABASE
Program membaca (READ ONLY):
C:\Analisis_Saham_BEI\BEI_Master_Output\BEI_Financial_Master.db

PERUBAHAN V2.3
- Memahami konteks arus kas tertentu pada format IDX yang menggunakan label
  CurrentYearInstant/PriorYearInstant meskipun nilai tersebut merupakan arus
  selama satu tahun. Syarat: jenis laporan cash_flow dan metadata tanggal
  (1 Jan–31 Dec untuk FY atau 1 Jan–akhir kuartal untuk YTD) harus cocok.
- Dua kolom komparatif diberi tahun data masing-masing.
- Mode Annual tidak mengklaim arus kas 9M sebagai FY.
- Neraca pembanding 31 Desember dari laporan interim tetap ditampilkan
  sebagai BS only dan REVIEW.
- Tahun paling baru disusun di kanan. Pilih sel untuk melihat sumber.
- Semua nilai RAW REVIEW, belum dinormalisasi satuan/mata uang antarlaporan.
- TTM, standalone quarter, valuasi, dan verifikasi PDF tidak diaktifkan.

UJI PADA DATA TERSEDIA
AALI FY2025 (sheet 1510000):
CFO 4,210,590; CFI -781,980; CFF -3,963,156;
Kas awal 3,236,012; kas akhir 2,755,715.
AALI FY2024 (komparatif dari FY2025): CFO 3,379,195.
Angka DI ATAS adalah angka mentah terambil dari database SQLite dan bukan
angka yang sudah diverifikasi terhadap PDF. Faktor skala belum disetujui.

KOMANDO UJI OPTIONAL
py test_v23.py
(Test script memakai database contoh bila tersedia. Dashboard tidak
bergantung pada test script.)

CATATAN KEAMANAN
File Excel/PDF dan seluruh database sumber tidak dimodifikasi atau dihapus.
Jika Windows Security mendeteksi ancaman, jangan mengabaikan peringatan.
