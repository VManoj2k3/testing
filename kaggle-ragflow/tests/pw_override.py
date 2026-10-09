"""pytest plugin for RAGFlow's Playwright suite (test/playwright): accept the tenant model IDs that
RAGFlow v1.0 itself uses ("model@instance@provider"). The suite's fixture only knows the older
"model@provider" form and otherwise skips every e2e test with "no canonical default llm_id".
Test-only; no RAGFlow code is changed. Usage: pytest -p pw_override test/playwright/e2e
"""


def pytest_configure(config):
    import test.playwright.conftest as c

    def _is_malformed(value):
        text = str(value or "").strip()
        if not text or "#" in text:
            return bool(text)
        parts = text.split("@")
        return not (2 <= len(parts) <= 3 and all(parts))
    c._is_malformed_tenant_model_value = _is_malformed
