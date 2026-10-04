import csv, io, json, os, re, secrets, time
from datetime import datetime
from functools import wraps

from flask import (Flask, Response, abort, flash, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)
from markupsafe import Markup, escape
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from db import close_db, init_db, q, run, setting
from security import (apply_headers, check_csrf, clean, csrf_token, is_negative_content, new_totp_secret,
                      rate_limit, totp_uri, verify_totp)

BASE = os.path.dirname(os.path.abspath(__file__))
INSTANCE = os.environ.get("INSTANCE_DIR", os.path.join(os.path.dirname(BASE), "instance"))
os.makedirs(os.path.join(INSTANCE, "uploads"), exist_ok=True)


def load_secret():
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    f = os.path.join(INSTANCE, "secret_key")
    if not os.path.exists(f):
        with open(f, "w") as fh:
            fh.write(secrets.token_hex(32))
        os.chmod(f, 0o600)
    return open(f).read().strip()


app = Flask(__name__)
app.config.update(
    SECRET_KEY=load_secret(),
    DB_PATH=os.path.join(INSTANCE, "portal.db"),
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 2,
    JSON_AS_ASCII=False,
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
init_db(app)
app.teardown_appcontext(close_db)
app.after_request(apply_headers)

SITE = "Pemerintah Kabupaten Muara Enim"


# ---------------------------------------------------------------- template helpers
@app.template_filter("paras")
def paras(text):
    out = []
    for block in re.split(r"\n\s*\n", text or ""):
        block = block.strip()
        if block:
            out.append("<p>" + "<br>".join(str(escape(l)) for l in block.split("\n")) + "</p>")
    return Markup("".join(out))


@app.template_filter("tgl")
def tgl(s):
    bulan = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    try:
        d = datetime.strptime((s or "")[:10], "%Y-%m-%d")
        return f"{d.day} {bulan[d.month]} {d.year}"
    except ValueError:
        return s or ""


@app.template_filter("mask_nik")
def mask_nik(n):
    n = n or ""
    return n[:6] + "••••••" + n[-4:] if len(n) == 16 else "••••"


@app.context_processor
def inject():
    return dict(csrf_token=csrf_token, site=SITE, cfg=lambda k: setting(k), is_admin=bool(session.get("uid")),
                year=datetime.now().year, admin_tables=CRUD)


@app.before_request
def csrf_guard():
    if request.method == "POST":
        check_csrf()


@app.errorhandler(400)
def e400(e):
    return render_template("error.html", kode=400, pesan=getattr(e, "description", "Permintaan tidak valid.")), 400


@app.errorhandler(404)
def e404(e):
    return render_template("error.html", kode=404, pesan="Halaman tidak ditemukan. Coba cari lewat kolom pencarian."), 404


@app.errorhandler(413)
def e413(e):
    return render_template("error.html", kode=413, pesan="Berkas terlalu besar. Maksimal 5 MB."), 413


@app.errorhandler(429)
def e429(e):
    return render_template("error.html", kode=429, pesan="Terlalu banyak permintaan. Tunggu beberapa menit lalu coba lagi."), 429


@app.errorhandler(500)
def e500(e):
    return render_template("error.html", kode=500, pesan="Terjadi gangguan di server. Coba lagi nanti."), 500


# ---------------------------------------------------------------- publik
@app.get("/")
def index():
    return render_template("index.html",
                           layanan=q("SELECT * FROM layanan ORDER BY id LIMIT 6"),
                           berita=q("SELECT * FROM berita ORDER BY tanggal DESC, id DESC LIMIT 3"),
                           jdih=q("SELECT * FROM jdih ORDER BY tahun DESC, id DESC LIMIT 3"))


@app.get("/halaman/<slug>")
def halaman(slug):
    h = q("SELECT * FROM halaman WHERE slug=?", (slug,), one=True)
    if not h:
        abort(404)
    return render_template("halaman.html", h=h)


@app.get("/berita")
def berita_list():
    return render_template("berita.html", items=q("SELECT * FROM berita ORDER BY tanggal DESC, id DESC"))


@app.get("/berita/<int:i>")
def berita_detail(i):
    b = q("SELECT * FROM berita WHERE id=?", (i,), one=True) or abort(404)
    return render_template("berita_detail.html", b=b)


# ---- Layanan perizinan / administrasi elektronik
@app.get("/layanan")
def layanan_list():
    return render_template("layanan.html", items=q("SELECT * FROM layanan ORDER BY id"))


ALLOWED = {b"%PDF": "pdf", b"\xff\xd8\xff": "jpg", b"\x89PNG": "png"}


def save_upload(f):
    if not f or not f.filename:
        return None
    head = f.read(4)
    f.seek(0)
    ext = next((e for sig, e in ALLOWED.items() if head.startswith(sig)), None)
    if not ext:
        abort(400, "Berkas harus PDF, JPG, atau PNG.")
    name = secrets.token_hex(16) + "." + ext
    f.save(os.path.join(INSTANCE, "uploads", name))
    return name


def new_ticket(prefix):
    return f"{prefix}-{datetime.now():%y%m%d}-{secrets.token_hex(3).upper()}"


@app.route("/layanan/<int:i>", methods=["GET", "POST"])
@rate_limit("izin", 8, 3600)
def layanan_form(i):
    l = q("SELECT * FROM layanan WHERE id=?", (i,), one=True) or abort(404)
    if request.method == "POST":
        nama = clean(request.form.get("nama"), 120)
        nik = re.sub(r"\D", "", request.form.get("nik", ""))
        kontak = clean(request.form.get("kontak"), 120)
        alamat = clean(request.form.get("alamat"), 300)
        ket = clean(request.form.get("keterangan"), 1500)
        err = None
        if request.form.get("website"):  # honeypot
            abort(400)
        if not (nama and kontak and alamat):
            err = "Nama, kontak, dan alamat wajib diisi."
        elif len(nik) != 16:
            err = "NIK harus 16 digit angka."
        elif request.form.get("setuju") != "1":
            err = "Anda perlu menyetujui Kebijakan Privasi."
        elif is_negative_content(nama, alamat, ket):
            err = "Isian ditolak karena mengandung konten yang dilarang."
        if err:
            flash(err, "error")
            return render_template("layanan_form.html", l=l, f=request.form), 400
        berkas = save_upload(request.files.get("berkas"))
        tiket = new_ticket("IZN")
        run("INSERT INTO perizinan(tiket,layanan_id,nama,nik,kontak,alamat,keterangan,berkas) VALUES(?,?,?,?,?,?,?,?)",
            (tiket, i, nama, nik, kontak, alamat, ket, berkas))
        return render_template("tiket.html", tiket=tiket, jenis="Permohonan layanan")
    return render_template("layanan_form.html", l=l, f={})


# ---- Pengaduan
KATEGORI = ["Pelayanan publik", "Infrastruktur dan lingkungan", "Kesehatan", "Pendidikan", "Perilaku petugas",
            "Konten negatif di ruang digital", "Lainnya"]


@app.route("/pengaduan", methods=["GET", "POST"])
@rate_limit("aduan", 6, 3600)
def pengaduan():
    if request.method == "POST":
        nama = clean(request.form.get("nama"), 120) or "Anonim"
        kontak = clean(request.form.get("kontak"), 120)
        kat = request.form.get("kategori")
        isi = clean(request.form.get("isi"), 3000)
        err = None
        if request.form.get("website"):
            abort(400)
        if kat not in KATEGORI:
            err = "Pilih kategori pengaduan."
        elif len(isi) < 20:
            err = "Uraian pengaduan minimal 20 karakter."
        elif request.form.get("setuju") != "1":
            err = "Anda perlu menyetujui Kebijakan Privasi."
        elif kat != "Konten negatif di ruang digital" and is_negative_content(nama, isi):
            err = "Pengaduan ditolak karena mengandung konten yang dilarang. Jika ingin melaporkan konten negatif, pilih kategori 'Konten negatif di ruang digital' dan jelaskan tanpa menyalin isinya."
        if err:
            flash(err, "error")
            return render_template("pengaduan.html", kategori=KATEGORI, f=request.form), 400
        tiket = new_ticket("ADU")
        run("INSERT INTO aduan(tiket,nama,kontak,kategori,isi) VALUES(?,?,?,?,?)", (tiket, nama, kontak, kat, isi))
        return render_template("tiket.html", tiket=tiket, jenis="Pengaduan")
    return render_template("pengaduan.html", kategori=KATEGORI, f={})


@app.route("/lacak", methods=["GET", "POST"])
@rate_limit("lacak", 20, 600)
def lacak():
    hasil = None
    if request.method == "POST":
        t = clean(request.form.get("tiket"), 40).upper()
        if t.startswith("ADU"):
            r = q("SELECT tiket,kategori AS jenis,status,tanggapan AS catatan,dibuat FROM aduan WHERE tiket=?", (t,), one=True)
        else:
            r = q("""SELECT p.tiket,l.nama AS jenis,p.status,p.catatan,p.dibuat FROM perizinan p
                     JOIN layanan l ON l.id=p.layanan_id WHERE p.tiket=?""", (t,), one=True)
        hasil = r or "tidak ada"
    return render_template("lacak.html", hasil=hasil)


# ---- JDIH
@app.get("/jdih")
def jdih():
    kw = clean(request.args.get("q"), 100)
    jenis = clean(request.args.get("jenis"), 60)
    tahun = request.args.get("tahun", type=int)
    page = max(request.args.get("hal", 1, type=int), 1)
    where, args = ["1=1"], []
    if kw:
        where.append("(judul LIKE ? OR nomor LIKE ?)")
        args += [f"%{kw}%"] * 2
    if jenis:
        where.append("jenis=?"); args.append(jenis)
    if tahun:
        where.append("tahun=?"); args.append(tahun)
    w = " AND ".join(where)
    total = q(f"SELECT COUNT(*) c FROM jdih WHERE {w}", args, one=True)["c"]
    rows = q(f"SELECT * FROM jdih WHERE {w} ORDER BY tahun DESC, id DESC LIMIT 15 OFFSET ?", args + [(page - 1) * 15])
    return render_template("jdih.html", rows=rows, total=total, page=page, pages=max((total + 14) // 15, 1),
                           jenis_list=[r[0] for r in q("SELECT DISTINCT jenis FROM jdih ORDER BY jenis")],
                           tahun_list=[r[0] for r in q("SELECT DISTINCT tahun FROM jdih ORDER BY tahun DESC")],
                           f=dict(q=kw, jenis=jenis, tahun=tahun))


# ---- Satu Data
@app.get("/satu-data")
def satu_data():
    return render_template("satu_data.html", items=q("SELECT d.*, (SELECT COUNT(*) FROM dataset_row r WHERE r.dataset_id=d.id) n FROM dataset d ORDER BY tahun DESC, id DESC"))


def _ds(i):
    d = q("SELECT * FROM dataset WHERE id=?", (i,), one=True) or abort(404)
    rows = q("SELECT label,nilai FROM dataset_row WHERE dataset_id=? ORDER BY id", (i,))
    return d, rows


@app.get("/satu-data/<int:i>")
def satu_data_detail(i):
    d, rows = _ds(i)
    return render_template("satu_data_detail.html", d=d, rows=rows,
                           chart=json.dumps([[r["label"], r["nilai"]] for r in rows]))


@app.get("/satu-data/<int:i>.csv")
def satu_data_csv(i):
    d, rows = _ds(i)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["label", f"nilai ({d['satuan']})"])
    for r in rows:
        lab = r["label"]
        w.writerow([("'" + lab) if lab[:1] in "=+-@" else lab, r["nilai"]])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="dataset-{i}.csv"'})


@app.get("/satu-data/<int:i>.json")
def satu_data_json(i):
    d, rows = _ds(i)
    return jsonify(judul=d["judul"], sektor=d["sektor"], tahun=d["tahun"], satuan=d["satuan"],
                   data=[dict(label=r["label"], nilai=r["nilai"]) for r in rows])


# ---- Publikasi
@app.get("/publikasi")
def publikasi():
    jenis = clean(request.args.get("jenis"), 40)
    rows = q("SELECT * FROM publikasi WHERE (?='' OR jenis=?) ORDER BY tahun DESC, id DESC", (jenis, jenis))
    return render_template("publikasi.html", rows=rows, jenis=jenis, jenis_list=[r[0] for r in q("SELECT DISTINCT jenis FROM publikasi")])


# ---- Kontak
@app.get("/kontak")
def kontak():
    return render_template("kontak.html")


# ---- Pencarian
@app.get("/cari")
def cari():
    kw = clean(request.args.get("q"), 100)
    res = {}
    if len(kw) >= 2:
        like = f"%{kw}%"
        res["Layanan"] = [(r["nama"], url_for("layanan_form", i=r["id"]), r["deskripsi"]) for r in q("SELECT * FROM layanan WHERE nama LIKE ? OR deskripsi LIKE ? LIMIT 8", (like, like))]
        res["Produk hukum"] = [(f'{r["jenis"]} No. {r["nomor"]}/{r["tahun"]}', url_for("jdih", q=r["nomor"], jenis=r["jenis"]), r["judul"]) for r in q("SELECT * FROM jdih WHERE judul LIKE ? OR nomor LIKE ? LIMIT 8", (like, like))]
        res["Dataset"] = [(r["judul"], url_for("satu_data_detail", i=r["id"]), r["sektor"]) for r in q("SELECT * FROM dataset WHERE judul LIKE ? OR sektor LIKE ? LIMIT 8", (like, like))]
        res["Publikasi"] = [(r["judul"], url_for("publikasi", jenis=r["jenis"]), f'{r["jenis"]} {r["tahun"]}') for r in q("SELECT * FROM publikasi WHERE judul LIKE ? LIMIT 8", (like,))]
        res["Berita"] = [(r["judul"], url_for("berita_detail", i=r["id"]), r["ringkasan"]) for r in q("SELECT * FROM berita WHERE judul LIKE ? OR isi LIKE ? LIMIT 8", (like, like))]
        res["Halaman"] = [(r["judul"], url_for("halaman", slug=r["slug"]), "") for r in q("SELECT * FROM halaman WHERE judul LIKE ? OR isi LIKE ? LIMIT 8", (like, like))]
        res = {k: v for k, v in res.items() if v}
    return render_template("cari.html", kw=kw, res=res)


# ---- Chatbot (berbasis FAQ)
@app.post("/api/chat")
@rate_limit("chat", 30, 600)
def chat():
    data = request.get_json(silent=True) or {}
    text = clean(str(data.get("q", "")), 300).lower()
    if not text:
        return jsonify(a="Silakan ketik pertanyaan Anda.")
    if is_negative_content(text):
        return jsonify(a="Maaf, pertanyaan ini tidak dapat diproses karena memuat konten yang dilarang.")
    words = set(re.findall(r"[a-z0-9]{3,}", text))
    best, score = None, 0
    for f in q("SELECT * FROM faq"):
        s = len(words & set(f["kata_kunci"].lower().split()))
        if s > score:
            best, score = f, s
    if best:
        return jsonify(a=best["jawaban"])
    for l in q("SELECT * FROM layanan"):
        if words & set(re.findall(r"[a-z0-9]{4,}", l["nama"].lower())):
            return jsonify(a=f'Layanan "{l["nama"]}": {l["deskripsi"]} Ajukan di menu Layanan.', link=url_for("layanan_form", i=l["id"]))
    return jsonify(a="Maaf, saya belum menemukan jawabannya. Coba kata kunci lain, gunakan kolom pencarian, atau hubungi petugas lewat halaman Hubungi Kami.", link=url_for("kontak"))


# ---- Utilitas
@app.get("/healthz")
def healthz():
    q("SELECT 1")
    return "ok"


@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /admin\nDisallow: /api\nSitemap: " + request.url_root + "sitemap.xml\n", mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap():
    base = request.url_root.rstrip("/")
    paths = ["/", "/layanan", "/pengaduan", "/lacak", "/jdih", "/satu-data", "/publikasi", "/berita", "/kontak"]
    paths += [f"/halaman/{r['slug']}" for r in q("SELECT slug FROM halaman")]
    xml = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    xml += "".join(f"<url><loc>{base}{p}</loc></url>" for p in paths) + "</urlset>"
    return Response(xml, mimetype="application/xml")


# ================================================================ ADMIN
def admin_required(fn):
    @wraps(fn)
    def w(*a, **kw):
        if not session.get("uid"):
            return redirect(url_for("admin_login"))
        return fn(*a, **kw)
    return w


@app.route("/admin/login", methods=["GET", "POST"])
@rate_limit("login", 10, 600)
def admin_login():
    if request.method == "POST":
        u = q("SELECT * FROM users WHERE username=?", (clean(request.form.get("username"), 60),), one=True)
        if u and u["locked_until"] > time.time():
            flash("Akun dikunci sementara karena terlalu banyak percobaan gagal. Coba lagi nanti.", "error")
        elif u and check_password_hash(u["pw_hash"], request.form.get("password", "")):
            run("UPDATE users SET failed=0 WHERE id=?", (u["id"],))
            session.clear()
            session["pre_uid"] = u["id"]
            session["pre_t"] = time.time()
            return redirect(url_for("admin_2fa"))
        else:
            if u:
                f = u["failed"] + 1
                run("UPDATE users SET failed=?, locked_until=? WHERE id=?", (f, time.time() + 900 if f >= 5 else 0, u["id"]))
                if f >= 5:
                    run("UPDATE users SET failed=0 WHERE id=?", (u["id"],))
            flash("Nama pengguna atau kata sandi salah.", "error")
    return render_template("admin/login.html")


@app.route("/admin/2fa", methods=["GET", "POST"])
@rate_limit("otp", 10, 600)
def admin_2fa():
    uid = session.get("pre_uid")
    if not uid or time.time() - session.get("pre_t", 0) > 300:
        return redirect(url_for("admin_login"))
    u = q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    setup = not u["totp_enabled"]
    secret = u["totp_secret"] if u["totp_secret"] else None
    if setup and not secret:
        secret = new_totp_secret()
        run("UPDATE users SET totp_secret=? WHERE id=?", (secret, uid))
    if request.method == "POST":
        if verify_totp(secret, request.form.get("kode", "")):
            if setup:
                run("UPDATE users SET totp_enabled=1 WHERE id=?", (uid,))
            session.clear()
            session.permanent = True
            session["uid"] = uid
            session["uname"] = u["username"]
            return redirect(url_for("admin_home"))
        flash("Kode OTP salah atau kedaluwarsa.", "error")
    return render_template("admin/otp.html", setup=setup, secret=secret if setup else None,
                           uri=totp_uri(secret, u["username"]) if setup else None)


@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.get("/admin")
@admin_required
def admin_home():
    c = lambda sql: q(sql, one=True)[0]
    return render_template("admin/home.html",
                           n_aduan=c("SELECT COUNT(*) FROM aduan WHERE status='Diterima'"),
                           n_izin=c("SELECT COUNT(*) FROM perizinan WHERE status='Diterima'"))


STATUS = ["Diterima", "Diproses", "Perlu perbaikan", "Selesai", "Ditolak"]


@app.get("/admin/aduan")
@admin_required
def admin_aduan():
    return render_template("admin/aduan.html", rows=q("SELECT * FROM aduan ORDER BY id DESC LIMIT 200"), status=STATUS)


@app.post("/admin/aduan/<int:i>")
@admin_required
def admin_aduan_update(i):
    st = request.form.get("status")
    if st in STATUS:
        run("UPDATE aduan SET status=?, tanggapan=? WHERE id=?", (st, clean(request.form.get("tanggapan"), 1500), i))
        flash("Pengaduan diperbarui.", "ok")
    return redirect(url_for("admin_aduan"))


@app.get("/admin/perizinan")
@admin_required
def admin_perizinan():
    rows = q("SELECT p.*, l.nama AS layanan FROM perizinan p JOIN layanan l ON l.id=p.layanan_id ORDER BY p.id DESC LIMIT 200")
    return render_template("admin/perizinan.html", rows=rows, status=STATUS)


@app.post("/admin/perizinan/<int:i>")
@admin_required
def admin_perizinan_update(i):
    st = request.form.get("status")
    if st in STATUS:
        run("UPDATE perizinan SET status=?, catatan=? WHERE id=?", (st, clean(request.form.get("catatan"), 1500), i))
        flash("Permohonan diperbarui.", "ok")
    return redirect(url_for("admin_perizinan"))


@app.get("/admin/berkas/<int:i>")
@admin_required
def admin_berkas(i):
    r = q("SELECT berkas FROM perizinan WHERE id=?", (i,), one=True)
    if not r or not r["berkas"]:
        abort(404)
    return send_from_directory(os.path.join(INSTANCE, "uploads"), r["berkas"], as_attachment=True)


@app.route("/admin/pengaturan", methods=["GET", "POST"])
@admin_required
def admin_pengaturan():
    keys = ["alamat", "telepon", "email", "jam_layanan", "whatsapp"]
    if request.method == "POST":
        for k in keys:
            run("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, clean(request.form.get(k), 300)))
        flash("Pengaturan disimpan.", "ok")
        return redirect(url_for("admin_pengaturan"))
    return render_template("admin/pengaturan.html", vals={k: setting(k) for k in keys})


@app.route("/admin/sandi", methods=["GET", "POST"])
@admin_required
def admin_sandi():
    if request.method == "POST":
        u = q("SELECT * FROM users WHERE id=?", (session["uid"],), one=True)
        new = request.form.get("baru", "")
        if not check_password_hash(u["pw_hash"], request.form.get("lama", "")):
            flash("Kata sandi lama salah.", "error")
        elif len(new) < 12 or not re.search(r"\d", new) or not re.search(r"[A-Za-z]", new):
            flash("Kata sandi baru minimal 12 karakter dan memuat huruf serta angka.", "error")
        else:
            run("UPDATE users SET pw_hash=? WHERE id=?", (generate_password_hash(new), u["id"]))
            flash("Kata sandi diganti.", "ok")
    return render_template("admin/sandi.html")


# ---- CRUD generik
CRUD = {
    "berita": dict(label="Berita", cols=["judul", "tanggal"], fields=[
        ("judul", "Judul", "text"), ("ringkasan", "Ringkasan", "text"), ("isi", "Isi berita", "area"), ("tanggal", "Tanggal", "date")]),
    "jdih": dict(label="Produk Hukum (JDIH)", cols=["jenis", "nomor", "tahun", "judul"], fields=[
        ("jenis", "Jenis (mis. Peraturan Daerah)", "text"), ("nomor", "Nomor", "text"), ("tahun", "Tahun", "int"),
        ("judul", "Tentang", "area"), ("status", "Status", "text"), ("url", "Tautan berkas (https://…)", "url")]),
    "dataset": dict(label="Dataset (Satu Data)", cols=["judul", "sektor", "tahun"], fields=[
        ("judul", "Judul dataset", "text"), ("sektor", "Sektor", "text"), ("tahun", "Tahun", "int"),
        ("satuan", "Satuan", "text"), ("deskripsi", "Deskripsi dan sumber", "area"), ("rows", "Data (satu baris per entri: label,nilai)", "rows")]),
    "publikasi": dict(label="Publikasi Anggaran dan Kinerja", cols=["jenis", "judul", "tahun"], fields=[
        ("jenis", "Jenis (Anggaran / Kinerja / Program Kerja)", "text"), ("judul", "Judul", "text"), ("tahun", "Tahun", "int"),
        ("deskripsi", "Deskripsi", "area"), ("url", "Tautan dokumen (https://…)", "url")]),
    "layanan": dict(label="Daftar Layanan", cols=["nama", "instansi"], fields=[
        ("nama", "Nama layanan", "text"), ("deskripsi", "Deskripsi", "area"), ("persyaratan", "Persyaratan (satu per baris)", "area"),
        ("estimasi", "Estimasi waktu", "text"), ("instansi", "Instansi penanggung jawab", "text")]),
    "faq": dict(label="Jawaban Chatbot", cols=["kata_kunci", "jawaban"], fields=[
        ("kata_kunci", "Kata kunci (dipisah spasi)", "text"), ("jawaban", "Jawaban", "area")]),
    "halaman": dict(label="Halaman Profil dan Kebijakan", cols=["slug", "judul"], pk="slug", noadd=True, fields=[
        ("judul", "Judul", "text"), ("isi", "Isi", "area")]),
}


def _cfg(t):
    return CRUD.get(t) or abort(404)


def _coerce(form, fields):
    vals = {}
    for name, label, kind in fields:
        if kind == "rows":
            continue
        v = clean(form.get(name), 20000 if kind == "area" else 500)
        if kind == "int":
            v = int(v) if v.isdigit() else None
        if kind == "url" and v and not re.match(r"^https?://", v):
            abort(400, "Tautan harus diawali http:// atau https://")
        vals[name] = v
    return vals


def _parse_rows(text):
    out = []
    for line in (text or "").splitlines():
        if "," in line:
            lab, _, val = line.rpartition(",")
            try:
                out.append((clean(lab, 120), float(val.strip().replace(" ", ""))))
            except ValueError:
                abort(400, f"Nilai tidak valid pada baris: {line[:60]}")
    return out


@app.get("/admin/data/<t>")
@admin_required
def admin_list(t):
    c = _cfg(t)
    pk = c.get("pk", "id")
    return render_template("admin/list.html", t=t, c=c, pk=pk, rows=q(f"SELECT * FROM {t} ORDER BY {pk} DESC"))


@app.route("/admin/data/<t>/form", methods=["GET", "POST"])
@app.route("/admin/data/<t>/form/<rid>", methods=["GET", "POST"])
@admin_required
def admin_form(t, rid=None):
    c = _cfg(t)
    pk = c.get("pk", "id")
    row = q(f"SELECT * FROM {t} WHERE {pk}=?", (rid,), one=True) if rid else None
    if rid and not row:
        abort(404)
    if request.method == "POST":
        vals = _coerce(request.form, c["fields"])
        if not vals.get(c["fields"][0][0]):
            flash("Kolom pertama wajib diisi.", "error")
        else:
            if row:
                sets = ", ".join(f"{k}=?" for k in vals)
                run(f"UPDATE {t} SET {sets} WHERE {pk}=?", list(vals.values()) + [rid])
                new_id = row["id"] if pk == "id" else None
            else:
                if c.get("noadd"):
                    abort(400)
                new_id = run(f"INSERT INTO {t}({', '.join(vals)}) VALUES({', '.join('?' * len(vals))})", list(vals.values()))
            if t == "dataset":
                did = new_id
                run("DELETE FROM dataset_row WHERE dataset_id=?", (did,))
                for lab, val in _parse_rows(request.form.get("rows")):
                    run("INSERT INTO dataset_row(dataset_id,label,nilai) VALUES(?,?,?)", (did, lab, val))
            flash("Tersimpan.", "ok")
            return redirect(url_for("admin_list", t=t))
    extra = ""
    if t == "dataset" and row:
        extra = "\n".join(f'{r["label"]},{r["nilai"]:g}' for r in q("SELECT * FROM dataset_row WHERE dataset_id=? ORDER BY id", (row["id"],)))
    data = dict(row) if row else {}
    if request.method == "POST":
        data = request.form
    data = dict(data)
    if t == "dataset":
        data["rows"] = request.form.get("rows", extra) if request.method == "POST" else extra
    return render_template("admin/form.html", t=t, c=c, row=data, rid=rid)


@app.post("/admin/data/<t>/hapus/<rid>")
@admin_required
def admin_delete(t, rid):
    c = _cfg(t)
    if c.get("noadd"):
        abort(400)
    if t == "dataset":
        run("DELETE FROM dataset_row WHERE dataset_id=?", (rid,))
    run(f"DELETE FROM {t} WHERE {c.get('pk', 'id')}=?", (rid,))
    flash("Dihapus.", "ok")
    return redirect(url_for("admin_list", t=t))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 8000)))
