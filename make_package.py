"""
make_package.py - 배포용 지퍼 생성 (불필요한 파일 제외)
실행: python make_package.py
"""
import os
import zipfile
from pathlib import Path

BASE = Path(__file__).parent

# 앱 버전 (app.py의 APP_VERSION과 동기화)
APP_VERSION = "1.3.5"
ZIP_NAME = BASE / f"quotation-analyzer-v{APP_VERSION}.zip"

# 제외할 디렉터리/파일 패턴
EXCLUDE_DIRS = {"__pycache__", ".venv", "venv", ".git", "node_modules"}
EXCLUDE_FILES = {
    f"quotation-analyzer-v{APP_VERSION}.zip",
    "cost_chart.png",
}
# 제외할 폴더 경로
EXCLUDE_PATHS = {BASE / "data" / "sample"}


def should_skip(path: Path) -> bool:
    # 제외 디렉터리 내부
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    if path in EXCLUDE_PATHS:
        return True
    if path.name in EXCLUDE_FILES:
        return True
    # data 폴더의 기존 규칙 파일 제외 (새로 시작)
    if "classification_rules.json" in str(path):
        return True
    return False


def main():
    if ZIP_NAME.exists():
        ZIP_NAME.unlink()

    count = 0
    with zipfile.ZipFile(ZIP_NAME, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BASE):
            root_path = Path(root)
            # 제외 디렉터리 건너뛰기
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                file_path = root_path / file
                if should_skip(file_path):
                    continue
                arcname = file_path.relative_to(BASE)
                zf.write(file_path, arcname)
                count += 1

    size_mb = ZIP_NAME.stat().st_size / (1024 * 1024)
    print(f"[완료] {ZIP_NAME.name} 생성 ({count}개 파일, {size_mb:.1f} MB)")
    print()
    print("동료에게 이 지퍼를 보내고:")
    print("  1) 압축 풀기")
    print("  2) '설치하고_실행.bat' 더블클릭")
    print("하면 됩니다. (Python 3.10+ 필요)")


if __name__ == "__main__":
    main()
