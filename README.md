# Echolens Intelligence

[Bahasa Indonesia](#bahasa-indonesia) | [English](#english)

---

## Bahasa Indonesia

**Echolens** adalah aplikasi web cerdas berbasis *Artificial Intelligence* (AI) yang dirancang untuk mengambil, mengklasifikasi, dan menginterogasi ribuan komentar YouTube secara instan. 

### Apa Itu Echolens?
Pernahkah Anda melihat video YouTube dengan puluhan ribu komentar dan penasaran apa pendapat mayoritas penonton, namun tidak punya waktu untuk membaca semuanya? Echolens hadir untuk menyelesaikan masalah itu. Aplikasi ini memadukan **IndoBERT** (AI spesialis bahasa Indonesia) untuk membaca sentimen komentar dengan kecepatan tinggi secara lokal, serta **Google Gemini** yang memungkinkan Anda *mengobrol* dan bertanya langsung seputar opini-opini di kolom komentar tersebut.

### Fitur Utama
1. **Official YouTube API Fetching**: Mengambil (*fetching*) ratusan hingga ribuan komentar video secara resmi, legal, dan aman menggunakan API resmi YouTube Data v3. (Bukan sekadar metode *scraping* ilegal).
2. **Local Sentiment Analysis (IndoBERT)**: Memproses sentimen audiens (Positif, Negatif, Netral) menggunakan model AI lokal dengan teknik *Hardware-Aware Batching*. Sistem akan mendeteksi apakah komputer Anda menggunakan CPU biasa atau GPU berat, lalu menyesuaikan kecepatan bacanya secara otomatis tanpa menyedot biaya API pihak ketiga!
3. **Contextual AI Chat (RAG)**: Anda bisa bertanya langsung kepada kumpulan komentar tersebut. Contoh: *"Apa keluhan utama netizen soal performa gaming HP ini?"* AI Gemini tidak akan menebak-nebak, melainkan akan membaca bukti nyata dari 20 komentar paling relevan di *database*, merangkumnya untuk Anda, dan melampirkan dari mana sumber komentarnya.
4. **Supabase PostgreSQL**: Echolens menggunakan [Supabase](https://supabase.com) (platform *open-source* alternatif Firebase) sebagai sistem *database* PostgreSQL *cloud* yang super cepat, aman, dan gratis.
5. **Dashboard Modern**: Tampilan antarmuka (UI) yang bersih, profesional, asinkron, dan sangat responsif, dikembangkan dengan React & Vite.

### Alur Kerja (Workflow) Bagaimana Echolens Bekerja?
1. **Input URL**: Anda menempelkan (*paste*) *link* video YouTube ke dalam aplikasi.
2. **Data Fetching**: *Backend* Echolens (berbasis FastAPI Python) akan menghubungi server YouTube untuk meminta seluruh data komentar dan menyimpannya secara rapi ke *database* Supabase Anda.
3. **Batch Classification**: Setelah tersimpan, sistem langsung membangunkan model AI IndoBERT di komputer Anda untuk membaca ratusan komentar tersebut, memberi label Positif/Negatif/Netral secara beruntun (*batch*).
4. **Interactive Chat**: Setelah selesai, Anda dapat masuk ke tab "AI Chat". Saat Anda bertanya, sistem mencari komentar-komentar dengan jumlah *likes* terbanyak dan relevan dari Supabase, lalu menyerahkan teks tersebut kepada Google Gemini Flash-Lite untuk diracik menjadi jawaban yang cerdas dan terpercaya.

---

### Cara Instalasi Lengkap (Tutorial Pemula)

Jangan khawatir jika Anda pemula, ikuti petunjuk langkah demi langkah ini dengan hati-hati.

**Persiapan Aplikasi yang Wajib Diinstal:**
1. **Python** (Versi 3.10 atau lebih baru) - Bahasa pemrograman untuk sistem *backend*.
2. **Node.js** (Versi 18 atau lebih baru) - Untuk menjalankan sistem *frontend* (tampilan web).
3. **Git** - Untuk mengunduh kode proyek ini.

**Langkah 1: Membuat Akun & Mendapatkan Kunci (API Keys)**
Echolens membutuhkan tiga layanan gratis pihak ketiga agar bisa beroperasi:
- **Supabase (Database)**: Buka [Supabase](https://supabase.com), buat akun, buat proyek baru bernama "Echolens". Buka menu *Settings* -> *Database*, lalu cari URL koneksi (*Connection String*) URI. Ganti kata sandi di URL tersebut dengan *password* yang Anda buat.
- **YouTube API Key**: Buka [Google Cloud Console](https://console.cloud.google.com/), buat proyek baru, aktifkan "YouTube Data API v3", dan buat "API Key" di menu *Credentials*.
- **Gemini API Key**: Buka [Google AI Studio](https://aistudio.google.com/), *login* menggunakan akun Google, lalu klik *Create API Key*.

**Langkah 2: Mengunduh Kode (Kloning)**
Buka *Terminal* atau *Command Prompt (CMD)* di komputer Anda, lalu ketik:
```bash
git clone https://github.com/Mysteriza/echolens.git
cd echolens
```

**Langkah 3: Konfigurasi Backend (Mesin Utama)**
Buka folder `backend`, lalu buat sebuah file baru bernama `.env`. Isi file tersebut dengan kunci-kunci yang sudah Anda dapatkan pada Langkah 1:
```env
DATABASE_URL=postgresql+asyncpg://postgres:[PASSWORD_SUPABASE_ANDA]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
YOUTUBE_API_KEY=KODE_API_YOUTUBE_ANDA
GEMINI_API_KEY=KODE_API_GEMINI_ANDA
```
*Catatan: Pastikan URL Supabase menggunakan awalan `postgresql+asyncpg://` agar sesuai dengan sistem kami.*

Selanjutnya, di terminal Anda (masih di dalam folder proyek utama), instal *library* yang dibutuhkan dan siapkan tabel *database*:
```bash
cd backend
python -m venv venv
venv\Scripts\activate   # (Ketik ini jika menggunakan Windows)
source venv/bin/activate # (Ketik ini jika menggunakan Mac/Linux)

pip install -r requirements.txt
alembic upgrade head
```

**Langkah 4: Konfigurasi Frontend (Tampilan Web)**
Buka terminal baru (biarkan terminal *backend* Anda yang sebelumnya tetap terbuka), arahkan ke folder `frontend`, dan instal kebutuhannya:
```bash
cd frontend
npm install
```

**Langkah 5: Menjalankan Aplikasi Echolens**
Kembali ke folder utama `echolens` di terminal, lalu jalankan perintah penjalan otomatis ini:
```bash
python run.py
```
Sistem akan otomatis menghidupkan *backend* API dan *frontend* antarmuka Anda. Sekarang, buka *browser* kesayangan Anda (Google Chrome / Edge) dan kunjungi: **http://localhost:5173**. Selamat menikmati Echolens!

---

## English

**Echolens** is an intelligent, Artificial Intelligence (AI) powered web application designed to fetch, classify, and interrogate thousands of YouTube comments instantly.

### What is Echolens?
Have you ever seen a YouTube video with tens of thousands of comments and wondered what the general audience thinks, but simply lacked the time to read through them? Echolens solves this. It combines **IndoBERT** (an AI specialized in the Indonesian language) for high-speed local sentiment analysis, and **Google Gemini**, allowing you to directly *chat* and inquire about the opinions within the comment section.

### Key Features
1. **Official YouTube API Fetching**: Securely and legally fetches hundreds to thousands of video comments using the official YouTube Data v3 API. (This is clean API fetching, not unregulated scraping).
2. **Local Sentiment Analysis (IndoBERT)**: Processes audience sentiment (Positive, Negative, Neutral) using a local AI model backed by a *Hardware-Aware Batching* technique. The system detects whether your machine uses a standard CPU or a heavy GPU, automatically adjusting the processing speed without racking up third-party API costs!
3. **Contextual AI Chat (RAG)**: Ask questions directly to the comment pool. Example: *"What is the main netizen complaint regarding this phone's gaming performance?"* The Gemini AI won't guess; instead, it will read the factual evidence from the 20 most relevant comments in the database, summarize them for you, and cite the exact comment sources.
4. **Supabase PostgreSQL**: Echolens utilizes [Supabase](https://supabase.com) (an open-source Firebase alternative) as a lightning-fast, secure, and free cloud PostgreSQL database system.
5. **Modern Dashboard**: A clean, professional, asynchronous, and highly responsive user interface built using React & Vite.

### Workflow: How Echolens Works
1. **URL Input**: You paste the YouTube video link into the application.
2. **Data Fetching**: The Echolens backend (Python FastAPI) contacts YouTube's servers to request all the comment data, neatly saving it into your Supabase database.
3. **Batch Classification**: Once saved, the system awakens the IndoBERT AI model on your local machine to read hundreds of comments, labeling them Positive/Negative/Neutral in consecutive batches.
4. **Interactive Chat**: Afterwards, you navigate to the "AI Chat" tab. When you ask a question, the system retrieves the most liked and relevant comments from Supabase, handing the text over to Google Gemini Flash-Lite to formulate a smart, evidence-based answer.

---

### Complete Installation Guide (Beginner Friendly)

Don't worry if you are a beginner, simply follow these step-by-step instructions carefully.

**Required Software to Install:**
1. **Python** (Version 3.10 or newer) - The programming language for the backend system.
2. **Node.js** (Version 18 or newer) - To run the frontend web interface.
3. **Git** - To download this project's code.

**Step 1: Create Accounts & Obtain API Keys**
Echolens requires three free third-party services to operate:
- **Supabase (Database)**: Go to [Supabase](https://supabase.com), create an account, and start a new project named "Echolens". Go to *Settings* -> *Database*, locate your *Connection String URI*. Replace the password placeholder with the password you created.
- **YouTube API Key**: Go to [Google Cloud Console](https://console.cloud.google.com/), create a new project, enable the "YouTube Data API v3", and generate an "API Key" under the *Credentials* menu.
- **Gemini API Key**: Go to [Google AI Studio](https://aistudio.google.com/), log in with your Google account, and click *Create API Key*.

**Step 2: Download the Code (Cloning)**
Open your *Terminal* or *Command Prompt (CMD)* on your computer and type:
```bash
git clone https://github.com/Mysteriza/echolens.git
cd echolens
```

**Step 3: Backend Configuration (The Engine)**
Open the `backend` folder and create a new file named `.env`. Fill this file with the keys you obtained in Step 1:
```env
DATABASE_URL=postgresql+asyncpg://postgres:[YOUR_SUPABASE_PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
```
*Note: Ensure the Supabase URL uses the prefix `postgresql+asyncpg://` to conform with our system.*

Next, in your terminal (while inside the main project folder), install the required libraries and prepare the database tables:
```bash
cd backend
python -m venv venv
venv\Scripts\activate   # (Type this if using Windows)
source venv/bin/activate # (Type this if using Mac/Linux)

pip install -r requirements.txt
alembic upgrade head
```

**Step 4: Frontend Configuration (Web Interface)**
Open a new terminal window (keep your previous backend terminal open), navigate to the `frontend` folder, and install the dependencies:
```bash
cd frontend
npm install
```

**Step 5: Running Echolens**
Return to the main `echolens` folder in your terminal, and execute this auto-runner script:
```bash
python run.py
```
The system will automatically boot up both the API backend and your frontend interface. Now, open your favorite browser (Google Chrome / Edge) and visit: **http://localhost:5173**. Enjoy using Echolens!
