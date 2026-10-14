"""
classification/rule_store.py - 사용자 분류 규칙 저장소 (로컬 JSON)
"""
import json
from datetime import datetime
from typing import Optional
from quotation_analyzer.config import RULES_FILE, DATA_DIR


class RuleStore:
    """
    사용자 분류 규칙을 로컬 JSON 파일에 저장/관리.
    - 규칙 추가, 수정, 삭제, 내보내기
    - 적용 이력 기록 (금액/전체 문장 저장 금지)
    """

    def __init__(self, rules_file=None):
        self.rules_file = rules_file or RULES_FILE
        self.rules = {}       # {keyword: category}
        self.history = []     # [{timestamp, keyword, category, action}]
        self._load()

    def _load(self):
        """규칙 파일 로드"""
        try:
            if self.rules_file.exists():
                with open(self.rules_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.rules = data.get("rules", {})
                    self.history = data.get("history", [])
        except (json.JSONDecodeError, FileNotFoundError):
            self.rules = {}
            self.history = []

    def _save(self):
        """규칙 파일 저장"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.rules_file, "w", encoding="utf-8") as f:
            json.dump(
                {"rules": self.rules, "history": self.history[-100:]},
                f,
                ensure_ascii=False,
                indent=2,
            )

    def add_rule(self, keyword: str, category: str) -> bool:
        """규칙 추가"""
        kw = keyword.strip()
        if not kw:
            return False
        self.rules[kw] = category
        self._log(kw, category, "add")
        self._save()
        return True

    def update_rule(self, old_keyword: str, new_keyword: str, category: str) -> bool:
        """규칙 수정"""
        if old_keyword not in self.rules:
            return False
        del self.rules[old_keyword]
        self.rules[new_keyword.strip()] = category
        self._log(new_keyword, category, "update")
        self._save()
        return True

    def delete_rule(self, keyword: str) -> bool:
        """규칙 삭제"""
        if keyword not in self.rules:
            return False
        category = self.rules.pop(keyword)
        self._log(keyword, category, "delete")
        self._save()
        return True

    def get_rules(self) -> dict:
        """모든 규칙 반환"""
        return dict(self.rules)

    def get_history(self, limit: int = 20) -> list:
        """최근 적용 이력 반환"""
        return self.history[-limit:]

    def export_rules(self) -> str:
        """규칙을 JSON 문자열로 내보내기"""
        return json.dumps(
            {"rules": self.rules, "exported_at": datetime.now().isoformat()},
            ensure_ascii=False,
            indent=2,
        )

    def learn_from_correction(
        self, name: str, spec: str, category: str
    ) -> Optional[str]:
        """
        사용자 수정에서 규칙 학습.
        품명에서 핵심 키워드를 추출해 저장.
        Returns: 저장된 키워드 (없으면 None)
        """
        # 품명에서 핵심 단어 추출 (2자 이상)
        text = f"{name} {spec}".strip()
        if not text:
            return None

        # 기존 규칙과 중복 확인
        from quotation_analyzer.utils.helpers import normalize_text
        norm_text = normalize_text(text)
        for kw in self.rules:
            if normalize_text(kw) in norm_text:
                return None  # 이미 규칙 존재

        # 품명 자체를 키워드로 사용 (단, 너무 길면 잘라냄)
        keyword = name.strip() if name else text[:20]
        if not keyword:
            return None

        self.add_rule(keyword, category)
        return keyword

    def _log(self, keyword: str, category: str, action: str):
        """이력 기록 (금액/전체 문장 저장 안 함)"""
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "keyword": keyword,
            "category": category,
            "action": action,
        })
