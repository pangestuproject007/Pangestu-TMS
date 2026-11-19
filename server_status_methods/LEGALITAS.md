# Rekapitulasi Legalitas dan Keamanan Metode Monitoring IMB & IMS

Dokumen ini menjelaskan aspek legalitas, kepatuhan keamanan, dan standar teknis terkait penggunaan metode penarikan status (monitoring) otomatis pada server bioskop **GDC Technology (SR-1000, SX-3000)** dan **Dolby Laboratories (IMS1000, IMS2000, IMS3000)**.

---

## 1. Status Hukum: 100% Legal dan Sah
Aktivitas monitoring ini bersifat legal karena memenuhi kriteria berikut:
* **Hak Milik/Izin Operasional**: Perangkat keras (IMB & IMS) yang dipantau berada di jaringan lokal dan dimiliki/dioperasikan secara sah oleh pihak bioskop Anda sendiri.
* **Pemanfaatan Antarmuka Resmi (Official API)**: Sistem monitoring ini tidak melakukan peretasan (*hacking*) atau pembobolan sistem keamanan. Koneksi dilakukan menggunakan jalur antarmuka pemrograman aplikasi (API) resmi yang disediakan oleh pabrikan perangkat:
  * **Dolby/Doremi**: Melalui SOAP Web Service resmi pada port `10000`.
  * **GDC SR-1000**: Melalui Web REST API resmi pada port `80`.
  * **GDC SX-3000**: Melalui FastCGI API (`websms.fcgi`) resmi pada port `80`.

---

## 2. Penggunaan Kredensial Resmi (Authorized Access)
* Otentikasi dilakukan menggunakan akun tingkat pengguna resmi yang disediakan oleh produsen untuk kebutuhan teknisi/operator bioskop, yaitu akun **`Maintenance`** dengan kata sandi **(disimpan di config.json / variabel lingkungan `TMS_DEFAULT_SERVER_PASS`)**.
* Tidak ada tindakan pemalsuan otentikasi atau pemakaian *backdoor* ilegal dalam proses ini.

---

## 3. Kepatuhan Keamanan Bioskop Digital (DCI Compliance)
* **Karakteristik Read-Only**: Skrip monitoring ini hanya melakukan operasi **pembacaan data (Read-Only)** untuk mengambil status jalannya pertunjukan (seperti status play/stop, judul playlist/SPL, judul film/CPL yang sedang aktif, dan durasi).
* **Tidak Ada Modifikasi Konten/Sistem**: Sistem monitoring tidak melakukan modifikasi parameter proyeksi, tidak mengutak-atik enkripsi konten film (KDM), dan tidak memodifikasi konfigurasi penting IMB/IMS.
* **Keamanan Hak Cipta Terjaga**: Rantai kepercayaan keamanan konten digital cinema (DCI Security Chain) tetap utuh 100% tanpa adanya celah kebocoran rekaman data video/audio film.

---

## 4. Standar Industri Terbuka
* Integrasi ini merupakan praktik umum dalam dunia ekosistem bioskop digital (*Digital Cinema Ecosystem*).
* Semua sistem manajemen bioskop komersial di dunia, yang dikenal sebagai **TMS (Theater Management System)** (seperti *UniqueX RosettaBridge*, *AAM Screenwriter*, *CineLister*, dll.), menggunakan protokol komunikasi jaringan yang serupa untuk memantau status studio secara terpusat demi efisiensi operasional pertunjukan.

---

*Disiapkan secara profesional sebagai panduan kepatuhan operasional IT Bioskop.*
