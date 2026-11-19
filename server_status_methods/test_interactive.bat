@echo off
title Uji Coba Status Server IMB & IMS
cls

echo ====================================================
echo      UTILITY UJI COBA STATUS SERVER BIOSKOP
echo ====================================================
echo.
echo Pilih Tipe Server IMB/IMS:
echo  [1] GDC SR-1000 (REST API / Terproteksi Login)
echo  [2] GDC SX-3000 (FastCGI / Tanpa Login)
echo  [3] Dolby IMS1000/2000/3000 (SOAP API)
echo.

set /p tipe="Pilih nomor (1-3): "
echo.

set /p ip="Masukkan IP Server target (contoh: 192.168.11.63): "
echo.

echo Menghubungkan ke target... mohon tunggu...
echo.

python "%~dp0test_interactive.py" "%tipe%" "%ip%"

echo.
echo ====================================================
echo Selesai. Tekan tombol apa saja untuk menutup jendela.
echo ====================================================
pause >nul
