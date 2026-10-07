# DND Bridge

Self-hosted AI API key bridge/proxy. Sambungkan API key provider AI milikmu (yang kompatibel OpenAI API), dapatkan key `dnd-...`, pakai di aplikasi AI favoritmu lewat endpoint `/v1` yang kompatibel OpenAI. Pemakaian (request + token) tercatat per key. Mendukung Worker Mode: akun AI pribadimu bisa menjawab request secara otomatis.

## Fitur

- Endpoint `/v1` kompatibel OpenAI: `chat/completions`, `completions`, `models`, termasuk streaming SSE
- Key `dnd-...` per provider atau per worker, bisa revoke/nonaktifkan kapan saja
- Dashboard: statistik, grafik 14 hari, pemakaian per key
- Worker mode: job queue + worker agent API
- Validasi provider otomatis via `GET {base_url}/models`
- Rate limit 60 req/menit per key
- Dark/light mode, responsif mobile + desktop
- Tanpa build step: backend FastAPI menyajikan frontend statis

## Struktur

```
dnd-bridge/
  backend/
    main.py            # seluruh backend (auth, provider, key, worker, proxy, usage)
    requirements.txt
    static/            # frontend (index.html, app.html, app.js, Tailwind CDN)
    data/              # sqlite db (dibuat otomatis, jangan di-commit)
  docs/
    DOKUMENTASI.md     # dokumentasi lengkap (bahasa Indonesia)
  Dockerfile
  .dockerignore
  README.md
```

## Jalankan Lokal

```bash
cd dnd-bridge
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# opsional: set secret JWT (wajib di production)
export JWT_SECRET="isi-dengan-string-acak-panjang"

uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Buka http://localhost:8000 (landing) dan http://localhost:8000/app (dashboard).

## Deploy (Railway / Koyeb / VPS)

Build dari `Dockerfile` di root repo. Service menjalankan:

```
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Env yang perlu diisi:

| Var | Wajib | Keterangan |
|---|---|---|
| `JWT_SECRET` | Ya (production) | String acak panjang untuk tanda tangan JWT |
| `PORT` | Tidak | Default 8000, biasanya diisi platform |

Catatan persistensi: database SQLite ada di `backend/data/dnd_bridge.db`. Di platform ephemeral (Railway/Koyeb tanpa volume), pasang volume ke `/app/backend/data` agar data tidak hilang saat redeploy. Alternatif: ganti ke Postgres (di luar cakupan versi ini).

## Cara Pakai Singkat

1. Buka `/app`, daftar akun, masuk.
2. Tab **Provider**: tambah provider (nama, base URL mis. `https://api.openai.com/v1`, API key). Koneksi divalidasi otomatis.
3. Tab **Key Saya**: buat key, pilih mode provider + provider. Salin key `dnd-...` yang tampil sekali.
4. Di aplikasi AI yang mendukung custom endpoint OpenAI, isi:
   - Base URL: `https://<host-kamu>/v1`
   - API Key: key `dnd-...` tadi
5. Pantau pemakaian di tab **Dashboard**.

Worker mode: lihat tab **Worker Saya** di dashboard dan `docs/DOKUMENTASI.md`.

## Keamanan

- Key `dnd-...` asli hanya tampil sekali; yang disimpan hanya hash SHA256.
- API key provider tidak pernah dikirim ke browser (hanya tampil tersamar).
- Jangan commit `backend/data/`. Set `JWT_SECRET` yang kuat di production.
- Ini self-hosted: kamu mempercayakan API key providermu ke servermu sendiri.
