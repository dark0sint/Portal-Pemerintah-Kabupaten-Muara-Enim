import os, secrets, sqlite3
from flask import g, current_app
from werkzeug.security import generate_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL,
  totp_secret TEXT, totp_enabled INTEGER DEFAULT 0, failed INTEGER DEFAULT 0, locked_until REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS halaman(slug TEXT PRIMARY KEY, judul TEXT, isi TEXT);
CREATE TABLE IF NOT EXISTS berita(id INTEGER PRIMARY KEY, judul TEXT, ringkasan TEXT, isi TEXT, tanggal TEXT);
CREATE TABLE IF NOT EXISTS jdih(id INTEGER PRIMARY KEY, jenis TEXT, nomor TEXT, tahun INTEGER, judul TEXT,
  status TEXT DEFAULT 'Berlaku', url TEXT);
CREATE TABLE IF NOT EXISTS dataset(id INTEGER PRIMARY KEY, judul TEXT, sektor TEXT, tahun INTEGER, satuan TEXT, deskripsi TEXT);
CREATE TABLE IF NOT EXISTS dataset_row(id INTEGER PRIMARY KEY, dataset_id INTEGER, label TEXT, nilai REAL);
CREATE TABLE IF NOT EXISTS publikasi(id INTEGER PRIMARY KEY, jenis TEXT, judul TEXT, tahun INTEGER, deskripsi TEXT, url TEXT);
CREATE TABLE IF NOT EXISTS faq(id INTEGER PRIMARY KEY, kata_kunci TEXT, jawaban TEXT);
CREATE TABLE IF NOT EXISTS layanan(id INTEGER PRIMARY KEY, nama TEXT, deskripsi TEXT, persyaratan TEXT, estimasi TEXT, instansi TEXT);
CREATE TABLE IF NOT EXISTS aduan(id INTEGER PRIMARY KEY, tiket TEXT UNIQUE, nama TEXT, kontak TEXT, kategori TEXT,
  isi TEXT, status TEXT DEFAULT 'Diterima', tanggapan TEXT, dibuat TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS perizinan(id INTEGER PRIMARY KEY, tiket TEXT UNIQUE, layanan_id INTEGER, nama TEXT, nik TEXT,
  kontak TEXT, alamat TEXT, keterangan TEXT, berkas TEXT, status TEXT DEFAULT 'Diterima', catatan TEXT,
  dibuat TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS kunjungan(hari TEXT PRIMARY KEY, jumlah INTEGER DEFAULT 0);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DB_PATH"], timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(_=None):
    db = g.pop("db", None)
    if db:
        db.close()


def q(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def run(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid


def setting(key, default=""):
    r = q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return r["value"] if r else default


DEFAULT_SETTINGS = {
    "alamat": "Belum diatur. Isi melalui Admin > Pengaturan.",
    "telepon": "-", "email": "-", "jam_layanan": "Senin–Jumat, 08.00–16.00 WIB", "whatsapp": "",
}

HALAMAN = {
    "profil": ("Selayang Pandang", "Kabupaten Muara Enim berada di Provinsi Sumatera Selatan dengan ibu kota Muara Enim.\n\nPortal ini adalah pintu layanan dan informasi resmi Pemerintah Kabupaten Muara Enim bagi masyarakat.\n\n[Admin: ganti teks ini dengan selayang pandang resmi, sejarah singkat, dan gambaran wilayah dari Bagian Humas/Diskominfo.]"),
    "visi-misi": ("Visi dan Misi", "Visi\n[Admin: isi visi resmi dari dokumen RPJMD yang berlaku.]\n\nMisi\n[Admin: isi misi resmi dari dokumen RPJMD yang berlaku.]"),
    "struktur": ("Struktur Organisasi", "[Admin: isi bagan dan susunan perangkat daerah sesuai Peraturan Bupati tentang Susunan Organisasi Perangkat Daerah yang berlaku.]"),
    "pimpinan": ("Pimpinan Daerah", "Bupati Muara Enim\n[Admin: isi nama dan biodata singkat.]\n\nWakil Bupati Muara Enim\n[Admin: isi nama dan biodata singkat.]\n\nSekretaris Daerah\n[Admin: isi nama dan biodata singkat.]"),
    "syarat-ketentuan": ("Syarat dan Ketentuan", "Dengan memakai portal ini, Anda setuju dengan ketentuan berikut.\n\n1. Portal ini dikelola Pemerintah Kabupaten Muara Enim untuk informasi publik dan layanan administrasi.\n2. Data yang Anda kirim harus benar dan menjadi tanggung jawab Anda. Data palsu dapat membatalkan permohonan dan dikenai sanksi sesuai hukum.\n3. Dilarang mengirim konten yang melanggar hukum, seperti perjudian, pornografi, ujaran kebencian, penipuan, atau ancaman. Sistem menyaring konten semacam ini secara otomatis dan menolaknya.\n4. Pengaduan yang dikirim tidak boleh memuat data pribadi orang lain tanpa dasar yang sah.\n5. Pemerintah daerah dapat memperbarui ketentuan ini. Versi terbaru selalu berlaku di halaman ini.\n6. Layanan ini ditujukan bagi pengguna berusia 18 tahun ke atas. Anak di bawah 18 tahun diwakili orang tua atau wali."),
    "kebijakan-privasi": ("Kebijakan Privasi", "Kebijakan ini menjelaskan cara Pemerintah Kabupaten Muara Enim mengelola data pribadi Anda sesuai Undang-Undang Nomor 27 Tahun 2022 tentang Pelindungan Data Pribadi (UU PDP).\n\nData yang kami kumpulkan\nNama, kontak (telepon atau email), NIK, alamat, isi pengaduan, dan berkas yang Anda unggah. Kami hanya meminta data yang diperlukan untuk memproses permohonan atau pengaduan Anda.\n\nTujuan penggunaan\nMemproses permohonan layanan, menindaklanjuti pengaduan, dan menghubungi Anda tentang status tiket. Data tidak dijual dan tidak dipakai untuk iklan.\n\nPenyimpanan dan keamanan\nSeluruh lalu lintas data memakai HTTPS. Akses panel petugas dilindungi kata sandi dan verifikasi dua langkah (OTP). NIK ditampilkan tersamar di daftar petugas. Data disimpan selama diperlukan untuk layanan dan kewajiban arsip, lalu dihapus atau dianonimkan.\n\nHak Anda\nAnda berhak mengakses, memperbaiki, dan meminta penghapusan data pribadi Anda, serta menarik persetujuan, sesuai UU PDP. Ajukan melalui halaman Hubungi Kami dengan menyebut nomor tiket.\n\nAnak-anak\nPortal tidak dirancang untuk mengumpulkan data anak di bawah 18 tahun secara langsung. Permohonan untuk anak diajukan orang tua atau wali.\n\nCookie\nKami hanya memakai cookie sesi yang diperlukan agar formulir aman. Tidak ada pelacak pihak ketiga dan tidak ada iklan.\n\n[Admin: lengkapi nama pejabat pengendali data pribadi dan kontak resminya.]"),
    "aksesibilitas": ("Pernyataan Aksesibilitas", "Portal ini dirancang agar dapat dipakai semua orang, termasuk penyandang disabilitas.\n\nFitur bantu: perbesar dan perkecil teks, tata letak rata kiri atau kanan, huruf ramah disleksia, kontras tinggi, dan pembaca suara (text-to-speech) di bilah Aksesibilitas di bagian atas setiap halaman. Seluruh halaman dapat dinavigasi dengan papan ketik, dan memakai label yang dapat dibaca pembaca layar.\n\nJika Anda menemukan hambatan akses, laporkan melalui halaman Hubungi Kami."),
}

LAYANAN = [
    ("Surat Keterangan Usaha (SKU)", "Bukti kegiatan usaha mikro dan kecil di wilayah Kabupaten Muara Enim.", "Fotokopi KTP pemohon\nAlamat dan jenis usaha\nFoto lokasi usaha (JPG/PDF)", "3 hari kerja", "Dinas terkait / Kecamatan"),
    ("Surat Keterangan Domisili", "Keterangan tempat tinggal atau kedudukan usaha di Kabupaten Muara Enim.", "Fotokopi KTP\nSurat pengantar RT/RW atau kepala desa/lurah", "2 hari kerja", "Kecamatan"),
    ("Persetujuan Bangunan Gedung (PBG)", "Pengajuan persetujuan pembangunan atau perubahan bangunan.", "Fotokopi KTP\nBukti kepemilikan tanah\nGambar rencana bangunan (PDF)", "Sesuai ketentuan perizinan", "Dinas PUPR / DPMPTSP"),
    ("Izin Penyelenggaraan Reklame", "Izin pemasangan reklame di wilayah Kabupaten Muara Enim.", "Fotokopi KTP\nDesain dan lokasi reklame\nSurat persetujuan pemilik lahan", "Sesuai ketentuan perizinan", "DPMPTSP"),
    ("Rekomendasi / Layanan Administrasi Lainnya", "Layanan administrasi lain yang belum terdaftar. Petugas akan mengarahkan Anda ke perangkat daerah yang tepat.", "Fotokopi KTP\nUraian kebutuhan", "Menyesuaikan", "Sesuai kebutuhan"),
]

FAQ = [
    ("jam layanan buka tutup", "Jam layanan: Senin–Jumat 08.00–16.00 WIB. Layanan online dapat diakses setiap saat."),
    ("aduan pengaduan lapor keluhan", "Kirim pengaduan di menu Pengaduan. Anda akan mendapat nomor tiket untuk memantau tindak lanjut di menu Lacak Tiket."),
    ("izin perizinan sku domisili pbg reklame", "Ajukan permohonan di menu Layanan. Pilih jenis layanan, isi data, lalu unggah berkas. Pantau statusnya dengan nomor tiket."),
    ("lacak status tiket cek", "Buka menu Lacak Tiket, masukkan nomor tiket (contoh ADU-… atau IZN-…) untuk melihat status."),
    ("perda peraturan hukum jdih", "Cari peraturan daerah dan produk hukum di menu JDIH. Anda dapat memfilter berdasarkan jenis dan tahun."),
    ("data statistik dataset satu data", "Dataset sektoral ada di menu Satu Data. Setiap dataset dapat diunduh dalam format CSV atau JSON."),
    ("anggaran apbd kinerja laporan", "Laporan anggaran dan kinerja ada di menu Publikasi."),
    ("alamat lokasi kantor", "Alamat dan kontak resmi ada di halaman Hubungi Kami."),
    ("privasi data pribadi pdp", "Kami mengelola data sesuai UU PDP. Baca selengkapnya di halaman Kebijakan Privasi."),
    ("lupa password login admin", "Panel admin hanya untuk petugas. Hubungi administrator sistem untuk mengatur ulang akun."),
]


def init_db(app):
    path = app.config["DB_PATH"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    for k, v in DEFAULT_SETTINGS.items():
        db.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (k, v))
    for slug, (judul, isi) in HALAMAN.items():
        db.execute("INSERT OR IGNORE INTO halaman VALUES(?,?,?)", (slug, judul, isi))
    if not db.execute("SELECT 1 FROM layanan").fetchone():
        db.executemany("INSERT INTO layanan(nama,deskripsi,persyaratan,estimasi,instansi) VALUES(?,?,?,?,?)", LAYANAN)
    if not db.execute("SELECT 1 FROM faq").fetchone():
        db.executemany("INSERT INTO faq(kata_kunci,jawaban) VALUES(?,?)", FAQ)
    if not db.execute("SELECT 1 FROM jdih").fetchone():
        db.executemany("INSERT INTO jdih(jenis,nomor,tahun,judul,status,url) VALUES(?,?,?,?,?,?)", [
            ("Peraturan Bupati", "21", 2022, "Susunan, Kedudukan, Tugas, Fungsi dan Struktur Organisasi Dinas Kependudukan dan Pencatatan Sipil", "Berlaku", "https://peraturan.bpk.go.id/Download/206253/Perbup%2021%20Tahun%202022.pdf"),
            ("Peraturan Bupati", "25", 2019, "Kelas Jabatan di Lingkungan Pemerintah Kabupaten Muara Enim", "Berlaku", "https://peraturan.bpk.go.id/Download/120768/Perbup%2025%20th%202019.pdf"),
            ("Peraturan Bupati", "11", 2019, "Tim Pertimbangan Pembangunan dan Pelayanan Publik (TKP4) Kabupaten Muara Enim", "Berlaku", "https://peraturan.bpk.go.id/Download/113164/Perbup%2011%20Tahun%202019-jdih.pdf"),
        ])
    if not db.execute("SELECT 1 FROM dataset").fetchone():
        cur = db.execute("INSERT INTO dataset(judul,sektor,tahun,satuan,deskripsi) VALUES(?,?,?,?,?)",
                         ("Contoh: Permohonan Layanan per Triwulan (data ilustrasi)", "Pelayanan Publik", 2025, "permohonan",
                          "DATA CONTOH untuk memperlihatkan fitur grafik dan unduhan. Ganti dengan data resmi lewat Admin > Dataset."))
        db.executemany("INSERT INTO dataset_row(dataset_id,label,nilai) VALUES(?,?,?)",
                       [(cur.lastrowid, l, v) for l, v in [("Triwulan I", 120), ("Triwulan II", 150), ("Triwulan III", 180), ("Triwulan IV", 210)]])
    if not db.execute("SELECT 1 FROM publikasi").fetchone():
        db.executemany("INSERT INTO publikasi(jenis,judul,tahun,deskripsi,url) VALUES(?,?,?,?,?)", [
            ("Anggaran", "APBD Kabupaten Muara Enim", 2026, "Ringkasan APBD. Admin: unggah tautan dokumen resmi.", ""),
            ("Kinerja", "Laporan Kinerja Instansi Pemerintah (LKjIP)", 2025, "Laporan kinerja tahunan. Admin: unggah tautan dokumen resmi.", ""),
            ("Program Kerja", "Rencana Kerja Pemerintah Daerah (RKPD)", 2026, "Program kerja tahunan daerah. Admin: unggah tautan dokumen resmi.", ""),
        ])
    if not db.execute("SELECT 1 FROM berita").fetchone():
        db.execute("INSERT INTO berita(judul,ringkasan,isi,tanggal) VALUES(?,?,?,date('now'))",
                   ("Portal layanan publik daring kini dapat diakses", "Ajukan layanan, kirim pengaduan, dan cari produk hukum dari ponsel atau komputer.",
                    "Pemerintah Kabupaten Muara Enim menyediakan portal layanan publik daring.\n\nAnda dapat mengajukan layanan administrasi, mengirim pengaduan, mencari produk hukum di JDIH, dan mengunduh dataset sektoral tanpa harus datang ke kantor.\n\nGunakan menu Lacak Tiket untuk memantau status permohonan Anda."))
    # Admin awal
    if not db.execute("SELECT 1 FROM users").fetchone():
        user = os.environ.get("ADMIN_USER", "admin")
        pw = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
        db.execute("INSERT INTO users(username,pw_hash) VALUES(?,?)", (user, generate_password_hash(pw)))
        if not os.environ.get("ADMIN_PASSWORD"):
            f = os.path.join(os.path.dirname(path), "ADMIN_PASSWORD_AWAL.txt")
            with open(f, "w") as fh:
                fh.write(f"username: {user}\npassword: {pw}\n(Hapus berkas ini setelah login pertama dan 2FA aktif.)\n")
            os.chmod(f, 0o600)
            print(f"[SETUP] Akun admin awal ditulis ke {f}")
    db.commit()
    db.close()
