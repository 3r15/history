#!/usr/bin/env python3
"""data/ 아래 나뉜 JSON을 검사한다.

    python3 build/merge.py            검사만
    python3 build/merge.py --write    검사 후 data/index.json 의 meta.n 갱신

사이트는 이 파일들을 그대로 fetch 하므로 병합 산출물을 따로 만들지 않는다.
이 스크립트가 하는 일은 '깨진 참조를 배포 전에 잡아내는 것' 하나다.
개념을 새로 쓴 뒤에는 반드시 한 번 돌린다.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TYPES = {"인물", "사건", "제도", "문화", "사료", "흐름"}
BLOCKS = {"text", "list", "table", "steps", "note", "quote"}

errors: list[str] = []
warns: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warns.append(msg)


def read(name: str):
    path = DATA / name
    if not path.exists():
        err(f"{name}: 파일이 없습니다")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        err(f"{name}: JSON 파싱 실패 — {e}")
        return None


def main() -> int:
    idx = read("index.json")
    if idx is None:
        report()
        return 1

    eras = {e["no"]: e for e in idx["eras"]}
    lecs = {l["no"]: l for l in idx["lectures"]}

    for no, lec in lecs.items():
        if lec["era"] not in eras:
            err(f"index.json: {no}강이 존재하지 않는 시대 {lec['era']}를 가리킵니다")

    # ---------- 개념 ----------
    con: dict[int, dict] = {}
    per_era_con: Counter = Counter()
    for e in eras:
        f = read(f"concepts-{e}.json")
        if f is None:
            continue
        for c in f.get("items", []):
            name = f"concepts-{e}.json/{c.get('no')}"
            no = c.get("no")
            if not isinstance(no, int):
                err(f"{name}: no 가 정수가 아닙니다")
                continue
            if no in con:
                err(f"{name}: 개념 번호 {no} 가 중복입니다")
                continue
            con[no] = c
            per_era_con[e] += 1

            if c.get("era") != e:
                err(f"{name}: era 가 파일({e})과 다릅니다 — {c.get('era')}")
            if c.get("lec") not in lecs:
                err(f"{name}: 존재하지 않는 차시 {c.get('lec')}")
            elif lecs[c["lec"]]["era"] != e:
                err(f"{name}: {c['lec']}강은 시대 {lecs[c['lec']]['era']} 소속인데 시대 {e} 파일에 있습니다")
            if c.get("type") not in TYPES:
                err(f"{name}: 알 수 없는 type — {c.get('type')}")
            if c.get("imp") not in (1, 2, 3):
                err(f"{name}: imp 는 1·2·3 중 하나여야 합니다 — {c.get('imp')}")
            if not str(c.get("title", "")).strip():
                err(f"{name}: title 이 비었습니다")
            body = c.get("body") or []
            if not body:
                err(f"{name}: body 가 비었습니다")
            for b in body:
                if b.get("type") not in BLOCKS:
                    err(f"{name}: 알 수 없는 블록 type — {b.get('type')}")

    # ---------- 문항 ----------
    qids: set[str] = set()
    per_era_q: Counter = Counter()
    for e in eras:
        f = read(f"quiz-{e}.json")
        if f is None:
            continue
        for q in f.get("questions", []):
            qid = q.get("id")
            name = f"quiz-{e}.json/{qid}"
            if not qid:
                err(f"quiz-{e}.json: id 가 없는 문항이 있습니다")
                continue
            if qid in qids:
                err(f"{name}: 문항 id 가 중복입니다")
                continue
            qids.add(qid)
            per_era_q[e] += 1

            if q.get("era") != e:
                err(f"{name}: era 가 파일({e})과 다릅니다 — {q.get('era')}")
            if q.get("lec") not in lecs:
                err(f"{name}: 존재하지 않는 차시 {q.get('lec')}")
            if not q.get("stem"):
                err(f"{name}: stem 이 비었습니다")
            for b in q.get("stem") or []:
                if b.get("type") not in BLOCKS:
                    err(f"{name}: 알 수 없는 stem 블록 — {b.get('type')}")

            opts = q.get("options") or []
            if not 2 <= len(opts) <= 5:
                err(f"{name}: 선택지가 {len(opts)}개입니다 (2~5개)")
            ans = q.get("answer")
            if not isinstance(ans, int) or not 1 <= ans <= len(opts):
                err(f"{name}: answer 가 선택지 범위를 벗어났습니다 — {ans}")
            texts = [str(o.get("text", "")).strip() for o in opts]
            if len(set(texts)) != len(texts):
                err(f"{name}: 같은 선택지가 두 번 있습니다")
            if any(not t for t in texts):
                err(f"{name}: 빈 선택지가 있습니다")
            if not str(q.get("why", "")).strip():
                warn(f"{name}: 해설(why)이 비었습니다")

            # refs 는 이 사이트의 취약 개념 모델이 딛고 서는 필드다.
            # 깨진 참조는 점수를 조용히 삼켜 버리므로 오류로 잡는다.
            for i, o in enumerate(opts, 1):
                if not o.get("refs"):
                    warn(f"{name}: {i}번 선택지에 refs 가 없어 오개념이 기록되지 않습니다")
                for r in o.get("refs") or []:
                    if r not in con:
                        err(f"{name}: {i}번 선택지가 없는 개념 {r} 을 가리킵니다")
            if not q.get("refs"):
                warn(f"{name}: 문항 refs 가 없습니다")
            for r in q.get("refs") or []:
                if r not in con:
                    err(f"{name}: 문항 refs 가 없는 개념 {r} 을 가리킵니다")

    # ---------- 분포 점검 ----------
    for e in eras:
        if per_era_con[e] and not per_era_q[e]:
            warn(f"시대 {e}({eras[e]['name']}): 개념은 있는데 문항이 하나도 없습니다")

    for no, lec in lecs.items():
        if lec.get("src") == "lecture" and not any(c["lec"] == no for c in con.values()):
            err(f"index.json: {no}강이 강의 반영(src=lecture)으로 표시됐지만 개념이 없습니다")

    if con:
        imp3 = sum(1 for c in con.values() if c["imp"] == 3)
        share = imp3 / len(con)
        if share > 0.5:
            warn(f"중요도 3(최빈출)이 전체의 {share:.0%}입니다. "
                 f"절반을 넘으면 필터로서 의미가 없으니 2로 내리세요")

    # ---------- 보고 ----------
    print(f"개념 {len(con)}개 · 문항 {len(qids)}개 · 차시 {len(lecs)}개")
    for e in sorted(eras):
        done = "" if per_era_con[e] else "   ← 수집 대기"
        print(f"  시대 {e} {eras[e]['name']:<22} 개념 {per_era_con[e]:>4}  문항 {per_era_q[e]:>4}{done}")

    if "--write" in sys.argv and not errors:
        p = DATA / "index.json"
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw.setdefault("meta", {})["n"] = {"con": len(con), "quiz": len(qids)}
        p.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("index.json meta.n 갱신")

    return report()


def report() -> int:
    for w in warns:
        print(f"경고  {w}")
    for e in errors:
        print(f"오류  {e}")
    if errors:
        print(f"\n{len(errors)}건의 오류가 있습니다.")
        return 1
    print(f"\n검사 통과 (경고 {len(warns)}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
