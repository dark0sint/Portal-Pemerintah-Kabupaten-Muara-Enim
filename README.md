# Portal Pemerintah Kabupaten Muara Enim

Aplikasi web siap jalan (Python/Flask + SQLite) yang dapat diakses publik dari ponsel dan komputer.

## Fitur

| Kelompok | Yang sudah ada |
|---|---|
| Keamanan dan privasi | Wajib HTTPS (nginx + Let's Encrypt, HSTS), login petugas dengan **OTP 2 langkah (TOTP)**, kunci akun setelah 5 gagal, proteksi CSRF, CSP ketat, batas laju (rate limit), validasi berkas (cek isi file, bukan hanya ekstensi), NIK ditampilkan tersamar, halaman **Syarat & Ketentuan** dan **Kebijakan Privasi** (UU PDP), persetujuan eksplisit di setiap formulir, **filter konten negatif** otomatis di formulir dan chatbot |
| Aksesibilitas | Bilah alat: perbesar/perkecil teks, rata kiri/kanan, huruf ramah disleksia, kontras tinggi, **pembaca suara** (bahasa Indonesia), tautan lompat ke konten, fokus papan ketik terlihat, label untuk pembaca layar. Tata letak responsif, tanpa framework dan tanpa sumber luar sehingga ringan |
| Transparansi | Profil (selayang pandang, visi-misi, struktur, pimpinan), **JDIH** dengan pencarian dan filter jenis/tahun, **Satu Data** dengan grafik + unduh CSV/JSON, **Publikasi** anggaran/kinerja/program kerja, berita, pencarian seluruh portal, sitemap |
| Layanan online | Permohonan layanan/perizinan dengan unggah berkas, nomor tiket, **Lacak Tiket**, **Pengaduan** (termasuk kategori konten negatif), Hubungi Kami, **chatbot** berbasis FAQ |
| Panel petugas | Menanggapi pengaduan, memproses permohonan, mengelola berita, JDIH, dataset, publikasi, layanan, FAQ chatbot, halaman profil/kebijakan, dan kontak, serta ganti sandi |
| Domain | Dikonfigurasi untuk domain `.go.id` (contoh `muaraenimkab.go.id`, ganti di `deploy/nginx.conf`) |

## Jalankan di server (Docker, direkomendasikan)

Prasyarat: server Ubuntu 22.04/24.04, Docker, nginx, certbot, domain sudah mengarah ke IP server.

```bash
git clone <repo> /srv/portal-muaraenim   # atau salin folder ini
cd /srv/portal-muaraenim
cp .env.example .env && nano .env        # isi SECRET_KEY, ADMIN_PASSWORD
docker compose up -d --build

sudo cp deploy/nginx.conf /etc/nginx/sites-available/portal-muaraenim
sudo ln -s /etc/nginx/sites-available/portal-muaraenim /etc/nginx/sites-enabled/
# terbitkan sertifikat dulu (nginx belum memuat blok 443 sebelum sertifikat ada):
sudo certbot certonly --nginx -d muaraenimkab.go.id -d www.muaraenimkab.go.id
sudo nginx -t && sudo systemctl reload nginx
```

Tanpa Docker: buat `python3 -m venv venv`, `venv/bin/pip install -r requirements.txt`, lalu pasang `deploy/portal.service`.

Uji cepat di komputer sendiri (tanpa HTTPS):

```bash
pip install -r requirements.txt
COOKIE_SECURE=0 ADMIN_PASSWORD='SandiUji12345' python app/app.py     # buka http://127.0.0.1:8000
python tests_smoke.py                                                 # 58 uji otomatis
```

## Login pertama petugas

1. Buka `/admin/login`, masuk dengan `ADMIN_USER` / `ADMIN_PASSWORD` dari `.env`.
2. Layar OTP menampilkan kunci rahasia. Masukkan ke aplikasi autentikator, lalu ketik kode 6 digit. OTP aktif permanen untuk akun itu.
3. Buka **Ganti sandi**, lalu isi konten resmi (di bawah).

## Wajib dilengkapi sebelum diumumkan ke publik

Aplikasi ini sengaja **tidak mengarang** data resmi. Hal berikut harus diisi/diurus instansi:

- **Konten resmi**: visi-misi, struktur organisasi, biodata pimpinan, selayang pandang (teks bertanda `[Admin: …]`). Isi di Admin → Halaman Profil dan Kebijakan.
- **Kontak resmi**: alamat, telepon, email di Admin → Pengaturan.
- **Lambang daerah**: ganti `app/static/img/logo.svg` dengan Lambang Daerah resmi.
- **Data contoh**: dataset "Contoh…" dan publikasi tanpa tautan hanyalah ilustrasi. Hapus atau ganti dengan dokumen resmi. Tiga entri JDIH awal bersumber dari peraturan.bpk.go.id, verifikasi sebelum tayang.
- **Daftar layanan dan persyaratan**: contoh generik, sesuaikan dengan SOP dan perangkat daerah penanggung jawab.
- **Domain `.go.id`**: pengajuan melalui PANDI/Komdigi oleh instansi. Setelah aktif, arahkan DNS ke server.
- **Kepatuhan**: pendaftaran PSE Lingkup Publik, penunjukan pengendali/pejabat data pribadi (UU PDP), dan penilaian keamanan (SNI ISO 27001 / uji penetrasi, koordinasi dengan BSSN) sesuai kebijakan daerah.

## Catatan teknis dan batasan yang jujur

- **OTP** memakai TOTP (aplikasi autentikator), bukan SMS. Berlaku untuk akun petugas, karena warga tidak perlu akun.
- **Filter konten** berbasis pola kata kunci. Ini lapis dasar, bukan moderasi canggih, dan petugas tetap perlu meninjau aduan. Pelindungan anak diterapkan lewat desain: tidak ada akun/profil publik, tidak ada konten buatan pengguna yang tampil publik, tanpa iklan dan pelacak, dan syarat usia 18+ atau diwakili wali.
- **Chatbot** berbasis kata kunci FAQ (dapat diubah petugas), bukan AI generatif. Mudah diganti ke LLM bila diperlukan.
- **Pembaca suara** memakai suara bawaan peramban pengguna. Ketersediaan suara bahasa Indonesia bergantung perangkat.
- **Rate limit** aplikasi dihitung per proses. Pembatas utama ada di nginx (`limit_req`).
- Database SQLite (mode WAL) cukup untuk trafik portal kabupaten pada umumnya. Bila perlu beban lebih besar, pindah ke PostgreSQL.
- NIK dan berkas disimpan di `instance/` tanpa enkripsi tingkat kolom: lindungi dengan enkripsi disk, izin file, dan cadangan terenkripsi (`deploy/backup.sh` sebagai awal).
- Pasang `deploy/backup.sh` di cron, dan perbarui dependensi secara berkala.
