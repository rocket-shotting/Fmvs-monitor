"""번역 누락 검사: 화면 문자열이 tr()로 감싸졌는지, 영어 사전에 있는지, 자리표시자가 같은지.

    python tests/check_i18n.py      (실패하면 종료 코드 1)

제외: 문서 문자열, log.* / logging 호출 인자, 파일 경로·이름, '# i18n: skip' 주석이 있는 줄."""
import ast
import os
import re
import string
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nvr_inspector")
sys.path.insert(0, ROOT)
HANGUL = re.compile("[가-힣]")
SKIP_FILES = {"i18n.py"}


def fields(s):
    try:
        return sorted({f for _t, f, _s, _c in string.Formatter().parse(s) if f})
    except ValueError:
        return None


def main():
    import i18n
    i18n.set_language("en")
    table = i18n._en
    problems = []
    for name in sorted(os.listdir(ROOT)):
        if not name.endswith(".py") or name in SKIP_FILES:
            continue
        path = os.path.join(ROOT, name)
        src = open(path, encoding="utf-8").read()
        lines = src.splitlines()
        tree = ast.parse(src)
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                body = node.body
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    docstrings.add(body[0].value)

        def in_log_call(node):
            p = parents.get(node)
            while p is not None:
                if isinstance(p, ast.Call):
                    f = p.func
                    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in ("log", "logging"):
                        return True
                p = parents.get(p)
            return False

        def tr_call(node):
            """node가 tr(...)의 첫 인자이면 True."""
            p = parents.get(node)
            return (isinstance(p, ast.Call) and isinstance(p.func, ast.Name) and p.func.id == "tr"
                    and p.args and p.args[0] is node)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
                if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    if node.args and not isinstance(node.args[0], ast.Constant):
                        continue          # tr(변수) – 상수 사전 값을 감싼 경우
                key = node.args[0].value
                if HANGUL.search(key):
                    if key not in table:
                        problems.append(f"{name}:{node.lineno}: 사전에 없음: {key!r}")
                    elif fields(key) != fields(table[key]):
                        problems.append(f"{name}:{node.lineno}: 자리표시자 불일치: {key!r} -> {table[key]!r}")
                    if node.keywords:
                        kw = sorted(k.arg for k in node.keywords if k.arg)
                        if fields(key) is not None and kw != fields(key):
                            problems.append(f"{name}:{node.lineno}: tr 인자 {kw} ≠ 자리표시자 {fields(key)}")
                continue
            if isinstance(node, ast.JoinedStr) and any(isinstance(v, ast.Constant) and HANGUL.search(str(v.value))
                                                      for v in node.values):
                if not in_log_call(node) and "i18n: skip" not in lines[node.lineno - 1]:
                    problems.append(f"{name}:{node.lineno}: 감싸지 않은 f-문자열 (tr(\"...{{x}}\", x=...)로)")
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and HANGUL.search(node.value):
                if node in docstrings or tr_call(node) or in_log_call(node):
                    continue
                if isinstance(parents.get(node), ast.JoinedStr):
                    continue
                if "i18n: skip" in lines[node.lineno - 1]:
                    continue
                # 모듈 상수(dict/list/tuple 안)는 표시할 때 tr(변수)로 감싸므로, 값이 사전에 있는지만 확인
                if node.value not in table:
                    problems.append(f"{name}:{node.lineno}: 사전에 없는 화면 문자열 또는 tr() 누락: {node.value[:60]!r}")
    for p in problems:
        print(p)
    print(f"번역 검사: 문제 {len(problems)}건 · 사전 {len(table)}개")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
