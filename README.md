# Tubes EAI – Sistem Akademik Kampus

Repository Tugas Besar mata kuliah Enterprise Application Integration (EAI).

## Tentang Proyek

Proyek ini bertujuan untuk mengintegrasikan beberapa sistem informasi yang digunakan dalam lingkungan perguruan tinggi, yaitu Sistem Informasi Akademik (SIAKAD), Sistem Keuangan/SPP, Sistem Perpustakaan, dan Sistem Presensi. Integrasi dilakukan menggunakan pendekatan Enterprise Application Integration (EAI) dengan RabbitMQ sebagai message broker untuk mendukung sinkronisasi data dan pertukaran informasi antar aplikasi secara otomatis.

## Anggota Kelompok

- Rizal Fatihul Ihsan (102022430034)
- Hafsya Khairin Nurwandi (102022400344)
- Nadia Sapitri (102022400063)

## Sistem yang Diintegrasikan

- Sistem Informasi Akademik (SIAKAD)
- Sistem Keuangan/SPP
- Sistem Perpustakaan
- Sistem Presensi

## Alur Integrasi

1. Mahasiswa melakukan daftar ulang melalui SIAKAD.
2. Informasi daftar ulang digunakan oleh Sistem Keuangan/SPP untuk membuat tagihan semester.
3. Setelah pembayaran dikonfirmasi, hak akses mahasiswa pada Sistem Perpustakaan diaktifkan.
4. Status mahasiswa aktif digunakan oleh Sistem Presensi untuk mendukung pencatatan kehadiran perkuliahan.

## Teknologi yang Digunakan

- FastAPI
- RabbitMQ
- Docker
- Docker Compose
- MySQL
- PostgreSQL
- SQLite
- Nginx API Gateway

