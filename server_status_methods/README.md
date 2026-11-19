# Metode Mendapatkan Play Status IMB (Integrated Media Block)

Folder ini berisi metode dan dokumentasi untuk membaca status playback, Show Playlist (SPL), dan Composition Playlist (CPL) yang sedang diputar di berbagai Integrated Media Block (IMB) bioskop digital.

## Daftar Isi
1. [GDC Technology (SX-3000 / SR-1000)](#1-gdc-technology-sx-3000--sr-1000)
2. [Dolby / Doremi (IMS1000 / IMS2000 / IMS3000 / ShowVault)](#2-dolby--doremi-ims1000--ims2000--ims3000--showvault)

---

## 1. GDC Technology (SX-3000 / SR-1000)
GDC Server menggunakan HTTP API FastCGI pada port `80` (untuk tipe SX-3000) atau REST API (untuk SR-1000).

* **File Implementasi**: [gdc_client.py](file:///d:/Projector%20Monitoring/server_status_methods/gdc_client.py)
* **Endpoint Utama**: `/cgi-bin/websms.fcgi?cmd=GetPlaystatus`
* **Metode**: HTTP GET
* **Format Kembalian**: JSON

---

## 2. Dolby / Doremi (IMS1000 / IMS2000 / IMS3000 / ShowVault)
Dolby/Doremi menggunakan SOAP Web Services XML pada port `10000`.

* **File Implementasi**: [dolby_client.py](file:///d:/Projector%20Monitoring/server_status_methods/dolby_client.py)
* **Service Endpoint**: `http://{IMS_IP}:10000/dc/dcp/ws/v1/ShowControl`
* **SOAP Action**: `GetShowStatus`
* **Metode**: HTTP POST
* **Format Kembalian**: XML (SOAP Envelope)
