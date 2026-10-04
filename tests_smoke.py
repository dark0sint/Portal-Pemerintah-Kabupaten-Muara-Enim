"""Uji asap: jalankan dengan `python tests_smoke.py`"""
import os, re, sys, tempfile, time
os.environ["INSTANCE_DIR"] = tempfile.mkdtemp()
os.environ["COOKIE_SECURE"] = "0"
os.environ["ADMIN_PASSWORD"] = "KataSandiUji12345"
sys.path.insert(0, "app")
import app as A
from security import _hotp
c = A.app.test_client()

def tok(path="/"):
    h = c.get(path).get_data(as_text=True)
    return re.search(r'name="csrf" content="([^"]+)"', h).group(1)

def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: ok.f += 1
ok.f = 0

for p in ["/", "/layanan", "/layanan/1", "/pengaduan", "/lacak", "/jdih", "/jdih?q=kelas", "/satu-data", "/satu-data/1",
          "/satu-data/1.csv", "/satu-data/1.json", "/publikasi", "/berita", "/berita/1", "/kontak", "/cari?q=usaha",
          "/halaman/kebijakan-privasi", "/halaman/profil", "/robots.txt", "/sitemap.xml", "/healthz", "/admin/login"]:
    r = c.get(p); ok(r.status_code == 200, f"GET {p} -> {r.status_code}")
ok(c.get("/nope").status_code == 404, "404 halaman")
r = c.get("/")
ok("frame-ancestors 'none'" in r.headers["Content-Security-Policy"] and r.headers["X-Frame-Options"] == "DENY", "header keamanan")
ok('style="' not in r.get_data(as_text=True), "tanpa inline style (CSP)")

# CSRF
ok(c.post("/pengaduan", data={"isi": "x"}).status_code == 400, "POST tanpa CSRF ditolak")

# Pengaduan
t = tok("/pengaduan")
r = c.post("/pengaduan", data={"csrf_token": t, "kategori": "Pelayanan publik", "isi": "Jalan rusak parah di depan sekolah dasar.", "setuju": "1", "kontak": "0812"})
m = re.search(r"(ADU-\d{6}-[0-9A-F]{6})", r.get_data(as_text=True)); ok(bool(m), "pengaduan menghasilkan tiket")
r = c.post("/pengaduan", data={"csrf_token": t, "kategori": "Pelayanan publik", "isi": "Daftar situs judi online slot gacor terbaik hari ini", "setuju": "1"})
ok(r.status_code == 400 and "dilarang" in r.get_data(as_text=True), "konten negatif diblokir")
r = c.post("/lacak", data={"csrf_token": t, "tiket": m.group(1)})
ok("Diterima" in r.get_data(as_text=True), "lacak tiket")
r = c.post("/lacak", data={"csrf_token": t, "tiket": "ADU-000000-AAAAAA"}); ok("tidak ditemukan" in r.get_data(as_text=True), "tiket palsu")

# Perizinan + upload
pdf = (__import__("io").BytesIO(b"%PDF-1.4 test"), "a.pdf")
r = c.post("/layanan/1", data={"csrf_token": t, "nama": "Budi", "nik": "1604010101010001", "kontak": "0812", "alamat": "Muara Enim", "setuju": "1", "berkas": pdf}, content_type="multipart/form-data")
ok("IZN-" in r.get_data(as_text=True), "permohonan layanan + unggah PDF")
bad = (__import__("io").BytesIO(b"MZ\x90 exe"), "a.pdf")
r = c.post("/layanan/1", data={"csrf_token": t, "nama": "Budi", "nik": "1604010101010001", "kontak": "0812", "alamat": "X", "setuju": "1", "berkas": bad}, content_type="multipart/form-data")
ok(r.status_code == 400, "berkas palsu (magic bytes) ditolak")
r = c.post("/layanan/1", data={"csrf_token": t, "nama": "Budi", "nik": "123", "kontak": "0812", "alamat": "X", "setuju": "1"})
ok(r.status_code == 400, "NIK tidak valid ditolak")

# Chatbot
r = c.post("/api/chat", json={"q": "jam layanan buka kapan"}, headers={"X-CSRF-Token": t}); ok("08.00" in r.get_json()["a"], "chatbot FAQ")
r = c.post("/api/chat", json={"q": "bokep"}, headers={"X-CSRF-Token": t}); ok("dilarang" in r.get_json()["a"], "chatbot filter konten")

# Admin + 2FA
ok(c.get("/admin").status_code == 302, "admin butuh login")
t = tok("/admin/login")
r = c.post("/admin/login", data={"csrf_token": t, "username": "admin", "password": "salah"}); ok("salah" in r.get_data(as_text=True), "login salah")
r = c.post("/admin/login", data={"csrf_token": t, "username": "admin", "password": "KataSandiUji12345"}); ok(r.status_code == 302 and "2fa" in r.location, "login -> 2FA")
ok(c.get("/admin").status_code == 302, "belum boleh masuk sebelum OTP")
h = c.get("/admin/2fa").get_data(as_text=True)
secret = re.search(r'class="ticket">([A-Z2-7]+)<', h).group(1)
t = re.search(r'name="csrf_token" value="([^"]+)"', h).group(1)
r = c.post("/admin/2fa", data={"csrf_token": t, "kode": "000000"}); ok("salah" in r.get_data(as_text=True), "OTP salah ditolak")
import base64
code = f"{_hotp(secret, int(time.time()//30)):06d}"
r = c.post("/admin/2fa", data={"csrf_token": t, "kode": code}); ok(r.status_code == 302 and r.location.endswith("/admin"), "OTP benar -> masuk")
for p in ["/admin", "/admin/aduan", "/admin/perizinan", "/admin/pengaturan", "/admin/sandi", "/admin/data/berita", "/admin/data/jdih",
          "/admin/data/dataset", "/admin/data/halaman", "/admin/data/berita/form", "/admin/data/dataset/form/1", "/admin/data/halaman/form/profil"]:
    r = c.get(p); ok(r.status_code == 200, f"admin GET {p} -> {r.status_code}")
t = tok("/admin")
r = c.post("/admin/data/dataset/form", data={"csrf_token": t, "judul": "Uji", "sektor": "X", "tahun": "2025", "satuan": "orang", "deskripsi": "d", "rows": "A,10\nB,20.5"})
ok(r.status_code == 302, "tambah dataset via CSV")
ok("20.5" in c.get("/satu-data/2.csv").get_data(as_text=True), "dataset baru bisa diunduh")
r = c.post("/admin/data/jdih/form", data={"csrf_token": t, "jenis": "Perda", "nomor": "1", "tahun": "2024", "judul": "T", "url": "javascript:alert(1)"})
ok(r.status_code == 400, "URL javascript: ditolak")
r = c.post("/admin/aduan/1", data={"csrf_token": t, "status": "Selesai", "tanggapan": "Sudah ditangani"})
t2 = tok("/lacak")
ok("Sudah ditangani" in c.post("/lacak", data={"csrf_token": t2, "tiket": m.group(1)}).get_data(as_text=True), "tanggapan petugas tampil ke warga")
ok(c.get("/admin/berkas/1").status_code == 200, "unduh berkas (admin)")
print("\nGAGAL:", ok.f); sys.exit(1 if ok.f else 0)
