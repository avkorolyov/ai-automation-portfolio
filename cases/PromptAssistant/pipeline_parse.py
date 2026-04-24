"""Парсинг выходов пайплайна ассистента (шаги 2, 6, 7 и метки [Промпт N])."""

import json
import re
from typing import cast


def extract_json_object(text: str) -> dict[str, object] | None:
    """Извлекает первый валидный JSON-объект из строки (по первой `{` до парной `}`)."""
    if not text or not text.strip():
        return None
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    quote = None
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if in_string:
            if c == "\\":
                escape = True
            elif c == quote:
                in_string = False
            continue
        if c in ("'", '"'):
            in_string = True
            quote = c
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start : i + 1])
                    return cast(dict[str, object], parsed) if isinstance(parsed, dict) else None
                except (json.JSONDecodeError, TypeError):
                    return None
    return None


def parse_step2(content: str) -> dict[str, object]:
    """Парсинг выхода шага 2: Есть_вопрос_к_клиенту, Вопрос_к_клиенту, Учесть_нейросеть, Сколько_генерируем_промптов."""
    result: dict[str, object] = {
        "needUserInput": False,
        "question": "",
        "учесть_нейросеть": "",
        "сколько_промптов": 1,
        "raw": None,
        "success": False,
    }
    o = extract_json_object(content)
    if not o:
        return result
    result["raw"] = o
    need = o.get("Есть_вопрос_к_клиенту")
    result["needUserInput"] = need in (1, "1", True)
    q = o.get("Вопрос_к_клиенту")
    result["question"] = q.strip() if isinstance(q, str) else ""
    u = o.get("Учесть_нейросеть")
    result["учесть_нейросеть"] = u.strip() if isinstance(u, str) else ""
    n = o.get("Сколько_генерируем_промптов")
    try:
        num = int(n) if isinstance(n, (int, float)) else int(n, 10) if isinstance(n, str) else 1
    except (ValueError, TypeError):
        num = 1
    result["сколько_промптов"] = num if num >= 1 else 1
    result["success"] = True
    return result


def parse_step6(content: str) -> dict[str, object]:
    """Парсинг выхода шага 6: оценка + замечания или массив по промптам."""
    result: dict[str, object] = {"raw": None, "success": False}
    o = extract_json_object(content)
    if not o:
        return result
    result["raw"] = o
    prompts_arr = o.get("промпты")
    if isinstance(prompts_arr, list):
        result["промпты"] = []
        for idx, item in enumerate(prompts_arr):
            num = item.get("номер", idx + 1) if isinstance(item, dict) else idx + 1
            oц = item.get("оценка") if isinstance(item, dict) else 0
            if isinstance(oц, (int, float)):
                oц = int(oц)
            elif isinstance(oц, str):
                try:
                    oц = int(oц)
                except ValueError:
                    oц = 0
            else:
                oц = 0
            зам = item.get("замечания") if isinstance(item, dict) else []
            result["промпты"].append({"номер": num, "оценка": oц, "замечания": зам if isinstance(зам, list) else []})
        result["success"] = True
        return result
    oц = o.get("оценка")
    if isinstance(oц, (int, float)):
        result["оценка"] = int(oц)
    elif isinstance(oц, str):
        try:
            result["оценка"] = int(oц)
        except ValueError:
            result["оценка"] = None
    else:
        result["оценка"] = None
    result["замечания"] = o.get("замечания") if isinstance(o.get("замечания"), list) else []
    result["success"] = True
    return result


def parse_step7(content: str) -> dict[str, object]:
    """Парсинг выхода шага 7: тип + промпты (массив строк). При неудаче — fallback: весь текст как один промпт."""
    fallback = lambda: {
        "тип": "один_промпт",
        "промпты": [content.strip()] if content and content.strip() else [],
        "raw": None,
        "success": False,
        "fallback": True,
    }
    if not content or not content.strip():
        return fallback()
    o = extract_json_object(content)
    if not o:
        return fallback()
    arr = o.get("промпты")
    if not isinstance(arr, list):
        return fallback()
    prompts = [p.strip() if isinstance(p, str) else str(p or "").strip() for p in arr]
    prompts = [p for p in prompts if p]
    if not prompts:
        return fallback()
    tip = "цепочка" if o.get("тип") == "цепочка" else "один_промпт"
    return {"тип": tip, "промпты": prompts, "raw": o, "success": True, "fallback": False}


def looks_like_filled_email_newsletter_json(text: str | None) -> bool:
    """
    Возвращает True, если текст содержит JSON вида готового письма (Subject + Body с заполненным контентом),
    а не мета-промпт с плейсхолдерами.

    Не срабатывает на шаблон с <тема письма>, короткими плейсхолдерами в Advantages и т.п.
    """
    if not text or not str(text).strip():
        return False
    o = extract_json_object(text)
    if not isinstance(o, dict):
        return False

    # Вариант GigaChat: { "subject": "...", "body": "длинный markdown" } без вложенного Body.Advantages
    subj_flat = o.get("subject") or o.get("Subject")
    body_flat = o.get("body") or o.get("Body")
    if isinstance(subj_flat, str) and isinstance(body_flat, str):
        ss = subj_flat.strip()
        bs = body_flat.strip()
        if len(ss) >= 12 and len(bs) >= 180:
            ssl = ss.lower()
            if "<тема" not in ssl and not (ssl.startswith("<") and ssl.endswith(">")):
                bsl = bs.lower()
                if any(
                    x in bsl
                    for x in (
                        "попробуйте",
                        "бесплатн",
                        "демо",
                        "присоединяйтесь",
                        "prompt assistant",
                        "промпт",
                        "**почему",
                        "**начните",
                    )
                ):
                    return True

    subj = o.get("Subject")
    body = o.get("Body")
    if not isinstance(subj, str) or not isinstance(body, dict):
        return False
    subj_s = subj.strip()
    if len(subj_s) < 12:
        return False
    sl = subj_s.lower()
    if "<тема" in sl or sl.startswith("<") and sl.endswith(">"):
        return False
    if "тема письма" in sl and ("<" in subj_s or "…" in subj_s):
        return False

    adv = body.get("Advantages")
    if isinstance(adv, list) and adv:
        pieces = [str(x).strip() for x in adv if x is not None and str(x).strip()]
        joined = " ".join(pieces)
        if len(joined) >= 100:
            placeholder_like = sum(
                1
                for p in pieces
                if p.startswith("<")
                or p.endswith(">")
                or "перечисление" in p.lower()
                or "ключевых преимуществ" in p.lower()
            )
            if placeholder_like < len(pieces) * 0.5:
                return True

    cta = body.get("CTA")
    if isinstance(cta, str) and len(cta.strip()) >= 60:
        cl = cta.lower()
        if "<" not in cta and "плейсхолдер" not in cl:
            if any(
                w in cl
                for w in (
                    "попробуйте",
                    "демо",
                    "бесплатн",
                    "регистрац",
                    "начните",
                    "узнайте",
                    "today",
                    "free",
                )
            ):
                return True

    gr = body.get("Greeting")
    if isinstance(gr, str) and len(gr.strip()) >= 20:
        if "Уважаемый" in gr and "{ИмяПользователя}" in gr and len(subj_s) > 15:
            if isinstance(adv, list) and adv:
                return True

    return False


def parse_prompts_with_markers(content: str) -> list[str]:
    """Разбивает текст по меткам [Промпт 1], [Промпт 2], … в массив строк."""
    if not content or not content.strip():
        return []
    pattern = re.compile(r"\[Промпт\s*(\d+)\]", re.IGNORECASE)
    parts = []
    last_end = 0
    for m in pattern.finditer(content):
        if m.start() > last_end:
            block = content[last_end : m.start()].strip()
            if block:
                parts.append(block)
        last_end = m.end()
    if last_end < len(content):
        block = content[last_end:].strip()
        if block:
            parts.append(block)
    return parts if parts else ([content.strip()] if content.strip() else [])
