# 🚀 배포 가이드

Streamlit 앱은 **서버 측 Python 처리**(파일 파싱·분류·집계)가 필수이므로
**정적 HTML 파일로 변환할 수 없습니다.** 아래 방법 중 상황에 맞게 선택하세요.

> 🔒 **기밀 데이터 주의**: 견적·원가 데이터가 포함되므로
> **Streamlit Cloud 등 외부 클라우드 배포는 비추천**입니다.
> 로컬 PC 또는 사내망 서버 배포를 권장합니다.

---

## 방법 ① 로컬 PC 실행 (가장 간단)

### 준비
```powershell
cd C:\Users\jonghun.kim\quotation-analyzer
pip install -r requirements.txt
```

### 실행
- **`실행.bat` 더블클릭** → 브라우저가 `http://localhost:8501`로 자동 열림
- 또는 터미널:
```powershell
python -m streamlit run app.py
```

### 다른 PC에서 실행 (같은 네트워크)
```powershell
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```
다른 PC에서 `http://<이_PC_IP>:8501` 접속.
(내 IP 확인: `ipconfig`)

---

## 방법 ② Docker 컨테이너 (사내망 서버 - 권장)

서버에 Docker만 설치되어 있으면 됩니다.

### 빌드 및 실행
```powershell
cd C:\Users\jonghun.kim\quotation-analyzer
docker compose up -d --build
```

### 접속
- 서버: `http://<서버_IP>:8501`
- 상태 확인: `docker compose logs -f`
- 중지: `docker compose down`

### 장점
- Python 환경 불필요 (컨테이너에 포함)
- `data/` 볼륨 마운트로 **분류 규칙 영구 저장**
- `restart: unless-stopped`로 자동 재시작
- OCR(tesseract) 포함

---

## 방법 ③ PyInstaller (.exe 단일 파일)

비개발자에게 Python 없이 배포할 때.

### 빌드
```powershell
pip install pyinstaller
pyinstaller --name "원가분석도구" --windowed --onefile ^
  --collect-all streamlit ^
  --collect-all plotly ^
  --collect-all pandas ^
  --collect-all openpyxl ^
  --collect-all pymupdf ^
  app.py
```

### 실행
- `dist/원가분석도구.exe` 생성
- 실행 시 브라우저가 자동 열림
- ⚠️ 파일 크기가 크고(수백 MB), 첫 실행이 느릴 수 있음
- ⚠️ antivirus가 오진할 수 있음 (Streamlit 내장 서버 때문)

> PyInstaller + Streamlit은 환경에 따라 추가 `--hidden-import`가
> 필요할 수 있습니다. 오류 시 `--hidden-import <모듈명>`을 추가하세요.

---

## 방법 ④ Nginx + systemd (사내망 프로덕션)

Docker 없이 Linux 서버에 직접 배포.

### 1. systemd 서비스
`/etc/systemd/system/quotation.service`:
```ini
[Unit]
Description=Quotation Analyzer
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/quotation-analyzer
ExecStart=/opt/quotation-analyzer/venv/bin/streamlit run app.py \
  --server.headless true --server.address 127.0.0.1 --server.port 8501
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now quotation
```

### 2. Nginx 리버스 프록시
`/etc/nginx/sites-available/quotation`:
```nginx
server {
    listen 80;
    server_name quotation.internal;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```
```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## 방법 ⑤ Streamlit Cloud (⚠️ 기밀 데이터 비추천)

GitHub 저장소 + Streamlit Cloud 연결.
**견적·원가 데이터가 외부 서버로 전송되므로 기밀 프로젝트에는 사용하지 마세요.**

---

## 보안 체크리스트 (배포 시)

| 항목 | 조치 |
|------|------|
| 외부 전송 | ❌ 없음 (로컬 처리) |
| 인증 | 사내망 접근 제한 / Nginx 기본 인증 추가 |
| HTTPS | Nginx + Let's Encrypt (사내 CA 가능) |
| 데이터 저장 | `data/` 폴더 접근 권한 제한 |
| 로그 | 견적 내용·금액 기록 없음 (이미 구현) |
| 파일 검증 | 확장자·크기 검증 (이미 구현) |

---

## 권장 선택

| 상황 | 추천 |
|------|------|
| 나만 사용 | ① 로컬 (`실행.bat`) |
| 팀이 사내망에서 사용 | ② Docker |
| 비개발자 배포 | ③ PyInstaller |
| 프로덕션 서버 | ④ Nginx + systemd |
