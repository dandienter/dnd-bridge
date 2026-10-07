# DOKUMENTASI LENGKAP - DND Bridge

*Self-hosted AI API Key Bridge/Proxy — versi 1.0.0*

---

## 0. Mulai Cepat - Dari Nol Sampai Request Pertama (5 Menit)

Instance live yang sudah jalan dan siap dipakai:

| Keperluan | URL |
|---|---|
| Dashboard (daftar, kelola provider/key) | `https://43-128-108-162.sslip.io/dnd-bridge/` |
| **Base URL untuk aplikasi AI** | `https://43-128-108-162.sslip.io/dnd-bridge/v1` |

> Penting: semua path diawali `/dnd-bridge`. URL tanpa itu (mis. `https://43-128-108-162.sslip.io/v1`) akan 404.

**Langkah 1 - Daftar.** Buka dashboard, klik **Daftar**, isi username + password. Kamu langsung masuk.

**Langkah 2 - Sambungkan provider.** Tab **Provider** -> **+ Tambah** -> isi:
- Nama: mis. `OpenAI`
- Base URL: `https://api.openai.com/v1` (atau provider OpenAI-compatible lain: OpenRouter, DeepSeek, Groq, Together, dsb.)
- API Key: key provider milikmu

Klik **Simpan**. Bridge otomatis memanggil `{base_url}/models` untuk validasi. Gagal = base URL/key salah.

**Langkah 3 - Buat key.** Tab **Key Saya** -> **+ Buat Key** -> nama bebas, mode **provider**, pilih provider -> **Buat**. **Salin key `dnd-...` sekarang juga** - hanya tampil sekali.

**Langkah 4 - Tes panggil.** Dari terminal/HP:

```bash
curl https://43-128-108-162.sslip.io/dnd-bridge/v1/chat/completions \
  -H "Authorization: Bearer dnd-KEYKAMU" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Halo!"}]}'
```

Balasan 200 berisi `choices[0].message.content` = sukses. Ganti `dnd-KEYKAMU` dengan key aslimu, dan `model` dengan model yang ada di providermu (cek `GET /v1/models`).

**Langkah 5 - Pakai di aplikasi AI.** Di aplikasi yang mendukung custom endpoint / OpenAI-compatible, isi:
- Base URL: `https://43-128-108-162.sslip.io/dnd-bridge/v1`
- API Key: `dnd-...` milikmu

**Langkah 6 - Pantau.** Tab **Dashboard**: total request & token hari ini, grafik 14 hari, rincian per key.

Selesai. Detail tiap langkah ada di bagian 5; referensi semua endpoint + contoh curl ada di bagian 6.

---

## Daftar Isi

0. [Mulai Cepat - Dari Nol Sampai Request Pertama](#0-mulai-cepat--dari-nol-sampai-request-pertama-5-menit)
1. [Pengenalan](#1-pengenalan)
2. [Konsep & Cara Kerja](#2-konsep--cara-kerja)
3. [Instalasi Lokal](#3-instalasi-lokal)
4. [Deploy ke Production](#4-deploy-ke-production)
5. [Panduan Penggunaan](#5-panduan-penggunaan)
   - 5.1. Akun: Daftar & Masuk
   - 5.2. Provider: Menyambungkan Provider AI
   - 5.3. Key Saya: Membuat & Mengelola Key dnd-
   - 5.4. Cara Sambung ke Aplikasi AI
   - 5.5. Dashboard & Statistik Pemakaian
   - 5.6. Worker Mode (Lengkap)
   - 5.7. Pengguna & Keluar
6. [Referensi API](#6-referensi-api)
7. [Keamanan](#7-keamanan)
8. [Troubleshooting](#8-troubleshooting)
9. [FAQ](#9-faq)

---

## 1. Pengenalan

**DND Bridge** adalah aplikasi self-hosted yang berfungsi sebagai jembatan (bridge/proxy) antara aplikasi AI di HP/komputermu dengan provider AI yang kamu pakai.

Masalah yang diselesaikan: banyak aplikasi AI (misalnya aplikasi chat AI pihak ketiga) meminta kamu mengisi *custom endpoint* yang kompatibel dengan OpenAI API. Kalau kamu punya beberapa API key dari provider berbeda, atau ingin memisahkan pemakaian per aplikasi sekaligus memantau siapa memakai berapa, DND Bridge memberi satu pintu terpusat:

- Kamu mendaftarkan API key provider AI milikmu **sekali** di dashboard.
- DND Bridge menerbitkan key **`dnd-...`** yang terikat ke provider (atau ke worker).
- Aplikasi AI-mu cukup diisi Base URL `https://<host-kamu>/v1` + key `dnd-...`, lalu dipakai seperti endpoint OpenAI biasa.
- Semua request tercatat: jumlah request dan token per key, plus grafik harian.

### Fitur utama

| Fitur | Keterangan |
|---|---|
| Proxy OpenAI-compatible | `POST /v1/chat/completions`, `POST /v1/completions`, `GET /v1/models`, streaming SSE |
| Key dnd- | Format `dnd-` + token acak, tampil sekali, bisa revoke/nonaktifkan |
| Validasi provider | `GET {base_url}/models` dipanggil otomatis saat provider disimpan |
| Dashboard | Kartu statistik, grafik 14 hari, rincian per key |
| Worker mode | Akun AI pribadimu menjawab request via job queue |
| Rate limit | 60 request/menit per key (HTTP 429 jika lewat) |
| Dark/light mode | Toggle tema, tersimpan di browser |
| Responsif | Sidebar di desktop, bottom navigation di HP |

---

## 2. Konsep & Cara Kerja

```
[Aplikasi AI di HP] --(Base URL: https://host/v1, Key: dnd-...)--> [DND Bridge]
                                                                        |
                                    +-------------------+-----------------+
                                    |                                     |
                              mode=provider                          mode=worker
                                    |                                     |
                          [Provider AI milikmu]                    [Job Queue]
                          (OpenAI / OpenRouter /                    |
                           dll, OpenAI-compatible)            [Worker AI pribadimu]
                                                                     polling tiap 5 mnt
```

1. **Mode provider**: DND Bridge meneruskan request ke `base_url` provider dengan API key provider yang tersimpan di server. Respons (termasuk streaming) diteruskan apa adanya ke aplikasi. Token usage dicatat dari field `usage` respons provider.
2. **Mode worker**: request tidak diteruskan ke provider. DND Bridge membuat *job* berisi `model` + `messages`, lalu menunggu (maksimal ~280 detik / 4,5 menit) sampai worker milikmu mengambil dan menjawabnya. Jawaban dikembalikan dalam format chat completion standar OpenAI.

**Yang tidak pernah terjadi**: API key provider aslimu tidak pernah dikirim ke browser atau ke aplikasi klien. Klien hanya memegang key `dnd-...`.

---

## 3. Instalasi Lokal

### Syarat

- Python 3.11+
- pip

### Langkah

```bash
cd dnd-bridge

# 1. Buat virtual environment (disarankan)
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependensi
pip install -r backend/requirements.txt

# 3. (Opsional tapi disarankan) set JWT secret
export JWT_SECRET="ganti-dengan-string-acak-minimal-32-karakter"

# 4. Jalankan
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Buka:

- Landing: http://localhost:8000/
- Dashboard: http://localhost:8000/app
- Health check: http://localhost:8000/api/health

Database SQLite dibuat otomatis di `backend/data/dnd_bridge.db` saat pertama dijalankan.

### Variabel environment

| Variabel | Default | Keterangan |
|---|---|---|
| `JWT_SECRET` | `dev-secret-change-me` | Secret penanda tangan JWT. **Wajib diganti di production** (ada warning di log jika memakai default) |
| `PORT` | `8000` | Port HTTP (dipakai Dockerfile) |

---

## 4. Deploy ke Production

### 4.1. Railway

1. Push repo ini ke GitHub.
2. Di Railway: New Project -> Deploy from GitHub -> pilih repo.
3. Railway otomatis mendeteksi `Dockerfile`.
4. Tambahkan variable: `JWT_SECRET` = string acak panjang (gunakan `openssl rand -hex 32`).
5. (Disarankan) Tambahkan Volume dan mount ke `/app/backend/data` agar database SQLite tidak hilang saat redeploy.
6. Railway memberi domain publik, mis. `https://dnd-bridge-production.up.railway.app`. Itulah host yang dipakai sebagai Base URL (`https://<domain>/v1`).

### 4.2. Koyeb

1. Push ke GitHub, buat service dari repo dengan builder Dockerfile.
2. Port: `8000`, health check path: `/api/health`.
3. Set env `JWT_SECRET`.
4. Untuk persistensi, gunakan Koyeb Volumes yang di-mount ke `/app/backend/data` (atau terima risiko data hilang saat redeploy).

### 4.3. VPS (Docker)

```bash
docker build -t dnd-bridge .
docker run -d --name dnd-bridge -p 8000:8000 \
  -e JWT_SECRET="isi-string-acak-panjang" \
  -v dnd-data:/app/backend/data \
  --restart unless-stopped \
  dnd-bridge
```

Tambahkan reverse proxy (Nginx/Caddy) + HTTPS di depan untuk production yang sesungguhnya.

### 4.4. VPS (tanpa Docker)

```bash
pip install -r backend/requirements.txt
JWT_SECRET="..." nohup uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
```

Gunakan systemd untuk auto-start (contoh unit file bisa dibuat mengikuti pola service lain di servermu).

---

## 5. Panduan Penggunaan

### 5.1. Akun: Daftar & Masuk

1. Buka `/app`.
2. Pilih tab **Daftar**, isi username (min. 3 karakter) dan password (min. 6 karakter), klik **Daftar**.
3. Kamu langsung masuk dan mendapat token JWT (tersimpan di `localStorage`, berlaku 7 hari).
4. Untuk masuk kembali, gunakan tab **Masuk**.

Semua data (provider, key, worker, log) terisolasi per akun.

### 5.2. Provider: Menyambungkan Provider AI

Buka tab **Provider** -> isi form **Tambah Provider**:

| Field | Contoh |
|---|---|
| Nama | `OpenAI`, `OpenRouter` |
| Base URL | `https://api.openai.com/v1` (tanpa trailing slash, otomatis dinormalisasi) |
| API Key Provider | `sk-...` milikmu |

Klik **Simpan & Validasi**. DND Bridge akan memanggil `GET {base_url}/models` dengan header `Authorization: Bearer <api-key>` (timeout 5 detik):

- Berhasil -> provider tersimpan, tampil di daftar dengan API key tersamar (`••••1234`).
- Gagal -> pesan error yang jelas, mis. *"API key ditolak provider (401 Unauthorized)"*, *"Timeout: provider tidak merespons dalam 5 detik"*, *"Tidak bisa terhubung ke base_url provider"*.

Provider tidak bisa dihapus selama masih ada key yang memakainya (hapus/nonaktifkan key-nya dulu).

### 5.3. Key Saya: Membuat & Mengelola Key dnd-

Buka tab **Key Saya** -> **+ Buat Key**:

1. **Nama Key**: mis. `key-hp`, `key-laptop` (untuk membedakan pemakaian per perangkat/aplikasi).
2. **Mode**:
   - *Provider*: teruskan ke provider AI. Wajib pilih provider.
   - *Worker*: dijawab worker AI milikmu (lihat 5.6).
3. Klik **Buat**.

Modal sukses menampilkan:

- **Key asli** (`dnd-...`) — tampil **sekali saja**, segera salin. Yang disimpan server hanya hash SHA256-nya.
- **Kotak "Cara Sambung"**: Base URL + key, siap salin.

Di daftar key kamu bisa:

- **Cara Sambung**: melihat kembali Base URL (key asli tidak bisa dilihat lagi).
- **Nonaktifkan/Aktifkan**: key nonaktif langsung ditolak (401).
- **Revoke**: hapus permanen.

### 5.4. Cara Sambung ke Aplikasi AI

Di aplikasi AI yang mendukung *custom endpoint / OpenAI-compatible*:

- **Base URL**: `https://43-128-108-162.sslip.io/dnd-bridge/v1` (instance live; kalau self-host sendiri: `https://<host-kamu>/v1`)
- **API Key**: key `dnd-...` milikmu
- **Model**: isi sesuai model yang tersedia di providermu (cek via `GET /v1/models` atau daftar provider)

Lalu pakai seperti biasa. Contoh dengan curl:

```bash
curl https://43-128-108-162.sslip.io/dnd-bridge/v1/chat/completions \
  -H "Authorization: Bearer dnd-xxxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Halo"}]}'
```

Contoh Python (openai lib):

```python
from openai import OpenAI
client = OpenAI(base_url="https://43-128-108-162.sslip.io/dnd-bridge/v1", api_key="dnd-xxxx")
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Halo"}],
)
print(resp.choices[0].message.content)
```

### 5.5. Dashboard & Statistik Pemakaian

Tab **Dashboard** menampilkan:

- **Total Key**, **Request Hari Ini**, **Token Hari Ini** (token = prompt + completion).
- **Grafik 14 hari terakhir**: batang jumlah request per hari (hover untuk detail).
- **Pemakaian per key**: total request & token tiap key.

Catatan: untuk request **streaming**, jumlah token dicatat 0 (token hanya bisa dihitung dari respons non-streaming yang memuat field `usage`), tapi request-nya tetap tercatat.

### 5.6. Worker Mode (Lengkap)

Worker mode memungkinkan **akun AI pribadimu** (misalnya akun ChatGPT/Claude/Gemini yang kamu beri instruksi khusus) menjadi "otak" di balik sebuah key.

#### Langkah 1: Buat worker

Tab **Worker Saya** -> **+ Buat Worker** -> isi nama -> **Buat**. Kamu dapat:

- **Token worker** (`dndw-...`): tampil sekali, segera salin.
- **Instruksi siap salin**: teks instruksi untuk ditempel ke akun AI-mu.

#### Langkah 2: Tempel instruksi ke akun AI-mu

Salin instruksi dari modal dan tempel ke akun AI milikmu (sebagai system prompt / instruksi kustom, tergantung platform AI-nya). Isi instruksi intinya:

1. Setiap 5 menit: `POST {host}/api/worker/ping` dengan header `Authorization: Bearer <token-worker>`.
2. Kalau `pending_jobs > 0`: `GET {host}/api/worker/jobs/next` (header sama) untuk mengambil job tertua `{id, model, messages}`.
3. Jawab isi `messages`, lalu `POST {host}/api/worker/jobs/{id}/answer` dengan body `{"text": "jawaban"}`.
4. Ulangi sampai tidak ada job (HTTP 204).

Status worker tampil **online** jika ia ping dalam 10 menit terakhir, beserta waktu terakhir terlihat.

#### Langkah 3: Buat key mode worker

Tab **Key Saya** -> **+ Buat Key** -> mode **Worker**. Key ini dipakai di aplikasi AI seperti biasa (Base URL + key `dnd-...`).

#### Alur request worker

1. Aplikasi memanggil `POST /v1/chat/completions` dengan key worker.
2. DND Bridge membuat job (`pending`) berisi model + messages.
3. Worker mengambil job (`claimed`), menjawab (`done`).
4. DND Bridge mengembalikan respons format chat completion OpenAI standar berisi teks jawaban worker.
5. Jika tidak ada worker yang menjawab dalam **~280 detik**: HTTP 504 dengan pesan jelas.

Batasan: worker mode hanya mendukung `/v1/chat/completions` (bukan `/v1/completions` maupun streaming).

#### Endpoint worker (untuk implementasi worker manual/bot)

| Method & Path | Auth | Keterangan |
|---|---|---|
| `POST /api/worker/ping` | Bearer token worker | Update last_seen, balas `{ok, pending_jobs}` |
| `GET /api/worker/jobs/next` | Bearer token worker | Ambil job tertua, tandai claimed; 204 jika kosong |
| `POST /api/worker/jobs/{id}/answer` | Bearer token worker | Body `{"text": "..."}`, tandai done |

### 5.7. Pengguna & Keluar

Tab **Pengguna** menampilkan username, tanggal bergabung, Base URL endpoint milikmu, dan tombol **Keluar** (menghapus token dari browser).

---

## 6. Referensi API (Lengkap + Contoh Panggil)

Konvensi di contoh: `BASE=https://43-128-108-162.sslip.io/dnd-bridge`, `JWT` = token dari register/login, `DNDKEY` = key `dnd-...`.

Semua endpoint `/api/*` (kecuali register/login/health) butuh header `Authorization: Bearer <jwt>`. Endpoint `/v1/*` butuh `Authorization: Bearer dnd-...`.

### Auth

| Method | Path | Body | Respon |
|---|---|---|---|
| POST | `/api/auth/register` | `{username, password}` | `{token, username}` |
| POST | `/api/auth/login` | `{username, password}` | `{token, username}` |
| GET | `/api/auth/me` | - | `{id, username, created_at}` |

```bash
# Daftar
curl -X POST $BASE/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"namakamu","password":"rahasia123"}'
# -> {"token":"eyJ...","username":"namakamu"}  (simpan tokennya)

# Masuk (kalau sudah punya akun)
curl -X POST $BASE/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"namakamu","password":"rahasia123"}'

# Cek user saat ini
curl $BASE/api/auth/me -H "Authorization: Bearer $JWT"
```

### Provider

| Method | Path | Body | Respon |
|---|---|---|---|
| GET | `/api/providers` | - | list (api_key tersamar) |
| POST | `/api/providers` | `{name, base_url, api_key}` | `{id, name, base_url}` / 400 |
| DELETE | `/api/providers/{id}` | - | `{ok}` / 400 jika dipakai key |

```bash
# Tambah provider (otomatis divalidasi via {base_url}/models)
curl -X POST $BASE/api/providers \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"name":"OpenAI","base_url":"https://api.openai.com/v1","api_key":"sk-..."}'

# Lihat daftar provider
curl $BASE/api/providers -H "Authorization: Bearer $JWT"

# Hapus provider
curl -X DELETE $BASE/api/providers/1 -H "Authorization: Bearer $JWT"
```

### Key

| Method | Path | Body | Respon |
|---|---|---|---|
| GET | `/api/keys` | - | list + ringkasan pemakaian |
| POST | `/api/keys` | `{name, mode, provider_id?}` | `{id, name, mode, key, key_prefix}` (key tampil sekali) |
| POST | `/api/keys/{id}/toggle` | - | `{ok, is_active}` |
| DELETE | `/api/keys/{id}` | - | `{ok}` |

`mode`: `provider` (terikat provider_id, proxy langsung) atau `worker` (masuk antrean job).

```bash
# Buat key mode provider (ganti provider_id dengan id dari daftar provider)
curl -X POST $BASE/api/keys \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"name":"HP Android","mode":"provider","provider_id":1}'
# -> {"id":1,"name":"HP Android","mode":"provider","key":"dnd-...","key_prefix":"dnd-Ab12"}

# Buat key mode worker
curl -X POST $BASE/api/keys \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"name":"Bot WA","mode":"worker"}'

# Nonaktifkan sementara / aktifkan lagi
curl -X POST $BASE/api/keys/1/toggle -H "Authorization: Bearer $JWT"

# Revoke (hapus permanen) - lakukan ini kalau key bocor
curl -X DELETE $BASE/api/keys/1 -H "Authorization: Bearer $JWT"
```

### Proxy (OpenAI-compatible) - Cara Panggil

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| GET | `/v1/models` | `dnd-` key | Diteruskan ke provider; key worker dapat daftar sintetis |
| POST | `/v1/chat/completions` | `dnd-` key | Non-streaming & SSE streaming; worker mode = antre job |
| POST | `/v1/completions` | `dnd-` key | Legacy completions (provider saja) |

```bash
# Daftar model
curl $BASE/v1/models -H "Authorization: Bearer $DNDKEY"

# Chat completion biasa
curl -X POST $BASE/v1/chat/completions \
  -H "Authorization: Bearer $DNDKEY" -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Halo"}]}'

# Chat completion streaming (SSE)
curl -N -X POST $BASE/v1/chat/completions \
  -H "Authorization: Bearer $DNDKEY" -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Halo"}],"stream":true}'

# Legacy completions
curl -X POST $BASE/v1/completions \
  -H "Authorization: Bearer $DNDKEY" -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","prompt":"Halo","max_tokens":50}'
```

Contoh Python (pakai lib `openai`):

```python
from openai import OpenAI
client = OpenAI(
    base_url="https://43-128-108-162.sslip.io/dnd-bridge/v1",
    api_key="dnd-KEYKAMU",
)
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Halo"}],
)
print(resp.choices[0].message.content)
```

Error umum: `401` key salah/nonaktif, `429` rate limit (60/mnt), `502` provider error, `504` worker timeout (tidak ada worker menjawab dalam ~280 detik).

### Usage

| Method | Path | Respon |
|---|---|---|
| GET | `/api/usage/summary` | `{per_key: [...], per_day: [...]}` (14 hari) |

```bash
curl $BASE/api/usage/summary -H "Authorization: Bearer $JWT"
```

### Worker (milik user, auth JWT)

| Method | Path | Respon |
|---|---|---|
| GET | `/api/workers` | list + status online |
| POST | `/api/workers` | `{id, name, token, token_prefix}` (token tampil sekali) |
| DELETE | `/api/workers/{id}` | `{ok}` |

```bash
# Buat worker (salin token dndw-... yang tampil sekali)
curl -X POST $BASE/api/workers \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"name":"akun-ai-ku"}'

# Lihat worker + status online
curl $BASE/api/workers -H "Authorization: Bearer $JWT"
```

### Worker agent (auth token worker)

`WTOKEN` = token `dndw-...` milik worker. Siklus polling yang disarankan tiap 5 menit.

```bash
# 1. Ping (lapor online + cek antrean)
curl -X POST $BASE/api/worker/ping \
  -H "Authorization: Bearer $WTOKEN"
# -> {"ok":true,"pending_jobs":2}

# 2. Ambil job tertua (204 = antrean kosong)
curl $BASE/api/worker/jobs/next \
  -H "Authorization: Bearer $WTOKEN"
# -> {"id":7,"model":"dnd-worker","messages":[...]}

# 3. Kirim jawaban
curl -X POST $BASE/api/worker/jobs/7/answer \
  -H "Authorization: Bearer $WTOKEN" -H "Content-Type: application/json" \
  -d '{"text":"Jawaban dari worker..."}'
# -> {"ok":true}
```

---

## 7. Keamanan

1. **Key `dnd-...` asli hanya tampil sekali** saat dibuat. Server menyimpan hash SHA256, bukan key-nya.
2. **API key provider tidak pernah ke browser**: endpoint list hanya mengembalikan 4 karakter terakhir tersamar.
3. **Password** di-hash dengan bcrypt.
4. **JWT** berlaku 7 hari; set `JWT_SECRET` yang kuat di production. Jangan pakai default.
5. **Rate limit** 60 req/menit per key mencegah abuse.
6. **Self-hosted = kamu yang dipercaya**: API key provider tersimpan plaintext di database serverMU. Amankan servermu (HTTPS, akses terbatas, backup). Jangan commit folder `backend/data/`.
7. Selalu gunakan **HTTPS** di production (Railway/Koyeb/VPS + reverse proxy menyediakan ini).

---

## 8. Troubleshooting

| Gejala | Penyebab umum & solusi |
|---|---|
| `404` di `/v1/*` atau `/api/*` (nginx) | Lupa prefix `/dnd-bridge`. Yang benar: `https://43-128-108-162.sslip.io/dnd-bridge/v1/...`, bukan `https://43-128-108-162.sslip.io/v1/...`. |
| `401 Invalid API key` di `/v1/*` | Key salah ketik, key di-revoke, atau key dinonaktifkan. Buat key baru / aktifkan lagi. |
| `401` di `/api/*` | Token JWT kedaluwarsa (7 hari). Masuk lagi. |
| `429 Rate limit exceeded` | Lebih dari 60 req/menit pada satu key. Kurangi frekuensi / pakai key terpisah. |
| `502 Provider error` | Provider down / base_url salah / API key provider invalid. Cek tab Provider, hapus lalu tambah ulang. |
| `504` pada key worker | Tidak ada worker online yang menjawab dalam ~280 detik. Pastikan worker ping rutin (tiap ≤5 menit) dan token benar. |
| Tambah provider gagal validasi | Pastikan base_url benar (tanpa path ganda `/v1/v1`), API key valid, dan server bisa menjangkau internet. |
| Data hilang setelah redeploy | Database SQLite ada di container/volume ephemeral. Pasang volume ke `/app/backend/data`. |
| Warning JWT_SECRET di log | Set env `JWT_SECRET` dengan string acak panjang, lalu restart. |
| Halaman `/app` blank | Pastikan `backend/static/` ikut ter-copy saat deploy (Dockerfile sudah melakukannya). Cek console browser. |

---

## 9. FAQ

**Apakah DND Bridge menyimpan isi chat saya?**
Request dicatat sebagai metadata (waktu, model, jumlah token, status, latensi) per key. Isi `messages` TIDAK disimpan untuk mode provider. Untuk mode worker, isi messages disimpan sementara sebagai job sampai dijawab, lalu bisa dihapus manual dari database jika perlu.

**Provider apa saja yang didukung?**
Semua yang kompatibel dengan OpenAI API (`/v1/models`, `/v1/chat/completions`): OpenAI, OpenRouter, DeepSeek, Together, Groq, Ollama (via tunnel), LiteLLM, dan lain-lain.

**Berapa banyak key yang bisa dibuat?**
Tidak dibatasi. Disarankan satu key per aplikasi/perangkat agar statistik pemakaian bermakna.

**Apakah streaming didukung?**
Ya, `stream: true` pada `/v1/chat/completions` diteruskan sebagai SSE. Token usage untuk streaming dicatat 0 (keterbatasan teknis).

**Bisakah dipakai rame-rame satu server?**
Bisa. Tiap user daftar akun sendiri; data terisolasi per user. Untuk publik, pertimbangkan rate limit dan monitoring.

**Bagaimana cara rotate key yang bocor?**
Tab Key Saya -> **Revoke** key lama -> **+ Buat Key** baru -> update aplikasi yang memakai key lama.

**Apakah worker bisa lebih dari satu per user?**
Bisa. Job diambil berdasarkan urutan tertua oleh worker mana pun milik user tersebut.

---

*Dokumentasi ini menyertai DND Bridge v1.0.0. Dibuat Oktober 2026.*
