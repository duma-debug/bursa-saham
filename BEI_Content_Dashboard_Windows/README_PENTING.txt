BEI CONTENT DASHBOARD — INVESTOR MANDIRI (Windows)

TUJUAN
Dashboard lokal untuk memilih ticker BEI, melihat perbandingan YoY awal,
menyiapkan artikel dan mengekspor PNG 1080x1350 (4:5) untuk Instagram.

PERSYARATAN
- Windows dengan Python 3.10+ (tkinter biasanya termasuk dalam instalasi Python resmi)
- matplotlib untuk menampilkan dan mengekspor grafik.
  Instal satu kali: py -m pip install matplotlib

LANGKAH INSTALL
1) Extract seluruh folder BEI_Content_Dashboard_Windows ke:
   C:\Analisis_Saham_BEI\BEI_Content_Dashboard_Windows
2) Pastikan salah satu database ini tersedia:
   C:\Analisis_Saham_BEI\BEI_Master_Output\BEI_Financial_Master.db
   atau C:\Analisis_Saham_BEI\financial_modeling_v4_1.db
3) Buka dashboard.pyw dengan Python. Jika asosiasi .pyw benar,
   double-click file tersebut langsung menampilkan aplikasi (tanpa CMD).
4) Jika double-click belum membuka aplikasi, gunakan CMD satu kali:
   cd /d C:\Analisis_Saham_BEI\BEI_Content_Dashboard_Windows
   pyw dashboard.pyw
5) Untuk akses desktop: klik kanan dashboard.pyw -> Show more options
   -> Send to -> Desktop (create shortcut), sesuai versi Windows.

PENGGUNAAN
- Ketik/pilih ticker, klik Analisis
- Tab Ringkasan: grafik YoY dari pasangan dalam filing sama
- Tab Perbandingan YoY: semua perbandingan awal
- Tab Draf Artikel: draf bisa dikoreksi di dalam aplikasi
- Tab Jejak Sumber: file asal + lokasi sel
- Klik Grafik PNG, Artikel .md atau Data .csv untuk ekspor

FILE OUTPUT
C:\Analisis_Saham_BEI\BEI_Dashboard_Output\<TICKER>\

BATASAN PENTING
- Aplikasi hanya MEMBACA database dalam mode read-only.
- Nilai mentah dari file berbeda bisa berbeda skala; grafik lintas filing
  dalam rupiah dengan sengaja TIDAK ditampilkan.
- Perhitungan YoY menggunakan CurrentYearDuration & PriorYearDuration
  dari sumber filing yang sama, tanpa verifikasi PDF.
- Perhitungan yang disajikan adalah REVIEW, bukan siap publikasi.
- Jika terdapat restatement atau perbedaan basis konsolidasi,
  wajib konfirmasi pada laporan keuangan asli.
- Grafik IG menampilkan peringatan REVIEW, perlu diverifikasi sebelum posting.
- Belum mendukung DCF, PER, PBV, EBITDA, atau TTM terverifikasi.
- Tidak menghapus atau mengubah database, Excel, atau PDF asli.
- Jika file .pyw diblokir, jangan matikan Windows Security; pastikan
  sumber file dipercaya dan periksa keamanan file sebelum menjalankan.
