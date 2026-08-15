# Echolens Intelligence 🔍🧠

[🇮🇩 Bahasa Indonesia](#-bahasa-indonesia) | [🇬🇧 English](#-english)

---

## 🇮🇩 Bahasa Indonesia

**Echolens** adalah aplikasi web cerdas (berbasis AI) yang dirancang untuk mengekstrak, mengklasifikasi, dan menginterogasi ribuan komentar YouTube secara instan. Echolens memadukan **IndoBERT** untuk analisis sentimen lokal berkecepatan tinggi dan **Google Gemini (RAG)** untuk fitur Chat interaktif yang memungkinkan Anda "berbicara" dengan komentar-komentar tersebut.

### 🌟 Fitur Utama
1. **Ekstraksi Komentar YouTube**: Mengambil ratusan hingga ribuan komentar dari video YouTube hanya dengan menempelkan URL.
2. **Local Sentiment Analysis (IndoBERT)**: Memproses sentimen komentar (Positif, Negatif, Netral) secara masif menggunakan *True Batching* (*hardware-aware*). Tidak memerlukan biaya API untuk klasifikasi!
3. **Retrieval-Augmented Generation (RAG) Chat**: Anda dapat bertanya kepada AI (Gemini) mengenai opini audiens. (Contoh: *"Apa keluhan utama netizen soal baterainya?"*). Sistem hanya akan menyaring 20 komentar paling relevan sebagai konteks untuk dijawab oleh Gemini, sehingga sangat akurat dan hemat kuota/biaya token API.
4. **Dashboard Modern**: Tampilan antarmuka (UI) yang bersih, profesional, asinkron, dan sangat responsif berbasis React & Vite.

### ⚙️ Alur Kerja (Workflow)
1. **Input URL**: Pengguna memasukkan URL video YouTube.
2. **Scraping**: `backend` (FastAPI) memanggil YouTube Data API v3 untuk mengunduh komentar ke dalam *database* PostgreSQL.
3. **Batch Classification**: Menggunakan model `indonesian-roberta-base-sentiment-classifier` dari HuggingFace, sentimen diproses secara masif (hingga 100 komentar sekaligus per kedipan mata, tergantung kekuatan CPU/GPU).
4. **Interactive Chat**: Pengguna masuk ke tab *AI Chat*. Saat bertanya, sistem akan melakukan *Semantic Search* pada database untuk mencari komentar relevan, lalu mengirimkannya ke Google Gemini Flash-Lite untuk disimpulkan menjadi sebuah jawaban.

### 🚀 Cara Instalasi

#### Persyaratan Sistem
- Python 3.10+
- Node.js 18+
- PostgreSQL (Pastikan server aktif dan berjalan)
- Akun Google AI Studio (Untuk *API Key* Gemini)
- Akun Google Cloud Console (Untuk *API Key* YouTube Data v3)

#### 1. Kloning Repositori
```bash
git clone https://github.com/Mysteriza/echolens.git
cd echolens
```

#### 2. Konfigurasi Backend (Python & PostgreSQL)
Buat file `.env` di folder `backend/`:
```env
DATABASE_URL=postgresql+asyncpg://postgres:password_anda@localhost:5432/echolens
YOUTUBE_API_KEY=KODE_API_YOUTUBE_ANDA
GEMINI_API_KEY=KODE_API_GEMINI_ANDA
```
Lalu instal dependensi dan jalankan migrasi *database*:
```bash
cd backend
python -m venv venv
venv\Scripts\activate   # (Untuk Windows)
pip install -r requirements.txt
alembic upgrade head
```

#### 3. Konfigurasi Frontend (React + Vite)
```bash
cd ../frontend
npm install
```

#### 4. Menjalankan Aplikasi
Anda dapat menjalankan *backend* dan *frontend* secara bersamaan menggunakan skrip orkestrasi yang telah disediakan:
```bash
python run.py
```
Buka *browser* Anda dan kunjungi `http://localhost:5173`.

---

## 🇬🇧 English

**Echolens** is an intelligent, AI-powered web application designed to instantly extract, classify, and interrogate thousands of YouTube comments. Echolens combines **IndoBERT** for high-speed local sentiment analysis (Indonesian language) and **Google Gemini (RAG)** for an interactive Chat feature that allows you to "talk" to the comments.

### 🌟 Key Features
1. **YouTube Comment Extraction**: Fetch hundreds to thousands of comments from any YouTube video just by pasting the URL.
2. **Local Sentiment Analysis (IndoBERT)**: Massively process comment sentiments (Positive, Negative, Neutral) using hardware-aware *True Batching*. No API costs required for classification!
3. **Retrieval-Augmented Generation (RAG) Chat**: Ask the AI (Gemini) about audience opinions (e.g., *"What is the main complaint about the battery?"*). The system filters the top 20 most relevant comments via semantic search as context for Gemini, ensuring highly accurate answers and saving massive token costs.
4. **Modern Dashboard**: A clean, professional, asynchronous, and highly responsive UI built with React & Vite.

### ⚙️ Workflow
1. **URL Input**: The user pastes a YouTube video URL.
2. **Scraping**: The `backend` (FastAPI) calls the YouTube Data API v3 to download comments into a PostgreSQL database.
3. **Batch Classification**: Using the `indonesian-roberta-base-sentiment-classifier` model from HuggingFace, sentiments are processed in massive batches (up to 100 comments at a time depending on CPU/GPU power).
4. **Interactive Chat**: The user navigates to the *AI Chat* tab. Upon asking a question, the system performs a *Semantic Search* to find relevant comments, then feeds them to Google Gemini Flash-Lite to formulate a conclusive answer.

### 🚀 Installation Guide

#### Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL (Ensure the server is active and running)
- Google AI Studio Account (For Gemini API Key)
- Google Cloud Console Account (For YouTube Data v3 API Key)

#### 1. Clone the Repository
```bash
git clone https://github.com/Mysteriza/echolens.git
cd echolens
```

#### 2. Backend Setup (Python & PostgreSQL)
Create a `.env` file inside the `backend/` directory:
```env
DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/echolens
YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
```
Then install dependencies and run database migrations:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # (For Linux/Mac) or venv\Scripts\activate (For Windows)
pip install -r requirements.txt
alembic upgrade head
```

#### 3. Frontend Setup (React + Vite)
```bash
cd ../frontend
npm install
```

#### 4. Running the Application
You can run both the *backend* and *frontend* concurrently using the provided orchestration script:
```bash
python run.py
```
Open your browser and navigate to `http://localhost:5173`.
