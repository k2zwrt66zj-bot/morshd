"""Validate question-import JSON records and load them into PostgreSQL.

Usage:
    python -I load_questions.py <records.json> [--dsn postgresql://...] [--dry-run]

Every record is validated against question-import.schema.json first. Loading
runs inside one transaction and relies on the database guards (one correct
option, publish gate, scoring gate, taxonomy consistency): if any guard
rejects a record, nothing is written.
"""
import argparse
import json
import pathlib
import sys
import uuid

import jsonschema

HERE = pathlib.Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / "question-import.schema.json").read_text(encoding="utf-8"))

# Normalizer shared with the ingestion worker (prototype until packages/core lands).
sys.path.insert(0, str(HERE.parents[2] / "research" / "prototypes"))
from arnorm import search_key  # noqa: E402

# AI_SUGGESTED_PENDING is a staging-only state: it never reaches the Question table.
BASIS_TO_DB = {
    "IN_SOURCE_FILE": "IN_SOURCE_FILE",
    "REFERENCE_VERIFIED": "REFERENCE_VERIFIED",
    "EDITOR_KEYED": "EDITOR_KEYED",
    "AI_SUGGESTED_VERIFIED": "AI_SUGGESTED_VERIFIED",
}
EXPLANATION_ORIGIN_TO_DB = {
    "FROM_SOURCE": "FROM_SOURCE",
    "TEAM_AUTHORED": "TEAM_AUTHORED",
    "AI_DRAFTED": "AI_DRAFTED",
    "FROM_SOURCE_PLUS_AI_DRAFTED": "AI_DRAFTED",
}


def cid() -> str:
    return "c" + uuid.uuid4().hex[:24]


def validate(records):
    v = jsonschema.Draft202012Validator(SCHEMA)
    problems = []
    for r in records:
        for e in v.iter_errors(r):
            problems.append(f"{r.get('id', '?')}: {'/'.join(map(str, e.path))}: {e.message}")
    return problems


def upsert(cur, sql_select, params_select, sql_insert, params_insert):
    cur.execute(sql_select, params_select)
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(sql_insert, params_insert)
    return cur.fetchone()[0]


def load(cur, r):
    q = r["question"]
    track_id = upsert(
        cur,
        'SELECT id FROM "Track" WHERE code = %s', (q["track"],),
        'INSERT INTO "Track"(id, code, "nameAr") VALUES (%s, %s, %s) RETURNING id',
        (cid(), q["track"], "الاختبار التخصصي: الإرشاد الطلابي" if q["track"] == "COUNSELOR" else "الاختبار التربوي العام"),
    )
    cat = q["category"]
    cat_id = upsert(
        cur,
        'SELECT id FROM "Category" WHERE "trackId" = %s AND code = %s', (track_id, cat["code"]),
        'INSERT INTO "Category"(id, "trackId", code, "nameAr") VALUES (%s, %s, %s, %s) RETURNING id',
        (cid(), track_id, cat["code"], cat["nameAr"]),
    )
    top = q["topic"]
    topic_id = upsert(
        cur,
        'SELECT id FROM "Topic" WHERE slug = %s', (top["slug"],),
        'INSERT INTO "Topic"(id, "categoryId", slug, "nameAr", "nameNorm") VALUES (%s, %s, %s, %s, %s) RETURNING id',
        (cid(), cat_id, top["slug"], top["nameAr"], search_key(top["nameAr"])),
    )

    source_ids = []
    for occ in q["occurrences"]:
        sid = upsert(
            cur,
            'SELECT id FROM "Source" WHERE title = %s', (occ["source"],),
            'INSERT INTO "Source"(id, type, title, rights, "yearHijri") VALUES (%s, %s, %s, %s, %s) RETURNING id',
            (cid(), occ["sourceType"], occ["source"], occ["rights"], occ.get("yearHijri")),
        )
        source_ids.append(sid)

    ref_id = None
    if q.get("answerRef"):
        ref_id = upsert(
            cur,
            'SELECT id FROM "Source" WHERE title = %s', (q["answerRef"]["source"],),
            'INSERT INTO "Source"(id, type, title, rights) VALUES (%s, %s, %s, %s) RETURNING id',
            (cid(), q["answerRef"].get("sourceType", "OFFICIAL"), q["answerRef"]["source"],
             q["answerRef"].get("rights", "OFFICIAL_PUBLIC")),
        )

    # A pending AI suggestion stays in staging (ExtractedQuestion) until a human verifies it.
    pending = q["answerBasis"] == "AI_SUGGESTED_PENDING"
    status = "IN_REVIEW" if (pending or r["review"]["status"] != "APPROVED") else "PUBLISHED"
    basis = BASIS_TO_DB.get(q["answerBasis"], "AI_SUGGESTED_VERIFIED")

    fam_id = cid()
    cur.execute('INSERT INTO "ItemFamily"(id, label) VALUES (%s, %s)', (fam_id, r["id"]))
    qid = cid()
    cur.execute(
        '''INSERT INTO "Question"(id, "trackId", "categoryId", "topicId", "familyId", type, stem, "stemNorm",
              difficulty, pool, origin, "keyNotInSource", "answerBasis", "answerConfidence",
              "answerRefSourceId", "answerRefPage", scorable, explanation, "explanationOrigin",
              reference, status, "updatedAt")
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())''',
        (qid, track_id, cat_id, topic_id, fam_id, q["type"], q["stem"], search_key(q["stem"]),
         q["difficulty"], q["pool"], q["origin"], q["keyNotInSource"], basis, q["answerConfidence"],
         ref_id, (q.get("answerRef") or {}).get("page"), q["scorable"] and not pending, q["explanation"],
         EXPLANATION_ORIGIN_TO_DB[q["explanationOrigin"]], q.get("reference"), status),
    )
    for i, o in enumerate(q["options"], 1):
        cur.execute(
            '''INSERT INTO "AnswerOption"(id, "questionId", label, text, "isCorrect", "fromSource", "whyWrong", "order")
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
            (cid(), qid, o["label"], o["text"], o["isCorrect"], o["fromSource"], o["whyWrong"], i),
        )
    for c in q["concepts"]:
        con_id = upsert(
            cur,
            'SELECT id FROM "Concept" WHERE "nameNorm" = %s', (search_key(c),),
            'INSERT INTO "Concept"(id, "topicId", "nameAr", "nameNorm") VALUES (%s, %s, %s, %s) RETURNING id',
            (cid(), topic_id, c, search_key(c)),
        )
        cur.execute(
            'INSERT INTO "QuestionConcept"("questionId", "conceptId") VALUES (%s, %s) ON CONFLICT DO NOTHING',
            (qid, con_id),
        )
    for occ, sid in zip(q["occurrences"], source_ids):
        cur.execute(
            '''INSERT INTO "QuestionOccurrence"(id, "questionId", "sourceId", page, "yearHijri", "rawExcerpt")
               VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
            (cid(), qid, sid, occ["page"], occ.get("yearHijri"), occ.get("rawExcerpt") or r["extraction"]["rawExcerpt"]),
        )
    return qid, status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("records")
    ap.add_argument("--dsn", default="postgresql://postgres@localhost:54330/swaa?host=/tmp")
    ap.add_argument("--dry-run", action="store_true", help="validate only")
    ap.add_argument("--keep", action="store_true", help="commit instead of rolling back")
    args = ap.parse_args()
    records = json.loads(pathlib.Path(args.records).read_text(encoding="utf-8"))
    problems = validate(records)
    if problems:
        print("INVALID:\n  " + "\n  ".join(problems))
        sys.exit(1)
    print(f"schema: {len(records)} records valid")
    if args.dry_run:
        return
    import psycopg
    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        for r in records:
            qid, status = load(cur, r)
            print(f"loaded {r['id']} -> Question {qid} ({status})")
        if args.keep:
            conn.commit()
            print("committed")
        else:
            conn.rollback()
            print("transaction rolled back (test load)")


if __name__ == "__main__":
    main()
