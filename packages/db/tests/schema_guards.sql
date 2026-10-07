-- Schema behaviour tests. Run against a fresh database after both migrations:
--   psql -v ON_ERROR_STOP=1 -f packages/db/tests/schema_guards.sql
-- Every block raises an exception on failure. Runs inside a rolled-back transaction.
BEGIN;

-- ---------- fixtures ----------
INSERT INTO "User"(id,name,email,role,"updatedAt") VALUES
  ('u_student','طالب','s@example.com','STUDENT',now()),
  ('u_admin','المؤسس','a@example.com','ADMIN',now());
INSERT INTO "Track"(id,code,"nameAr") VALUES ('t_c','COUNSELOR','الاختبار التخصصي: الإرشاد الطلابي');
INSERT INTO "Category"(id,"trackId",code,"nameAr") VALUES ('c1','t_c','C1','تعديل السلوك');
INSERT INTO "Topic"(id,"categoryId",slug,"nameAr","nameNorm") VALUES ('tp1','c1','behaviour-mod','الإقصاء','الاقصاء');
INSERT INTO "Source"(id,type,title,rights) VALUES
  ('src_recall','RECALLED_EXAM','استرجاع 1440','ANALYSIS_ONLY'),
  ('src_ref','BOOK','مرجع علمي','OFFICIAL_PUBLIC');
INSERT INTO "ItemFamily"(id) VALUES ('fam1');
INSERT INTO "Question"(id,"trackId","categoryId","topicId","familyId",stem,"stemNorm",origin,"answerBasis","answerConfidence","answerRefSourceId",explanation,"explanationOrigin",status,scorable,"createdById","answerVerifiedById","updatedAt")
VALUES ('q1','t_c','c1','tp1','fam1','سؤال','سوال','BASED_ON_RECALL','REFERENCE_VERIFIED','VERIFIED','src_ref','شرح','TEAM_AUTHORED','PUBLISHED',true,'u_admin','u_admin',now());
INSERT INTO "AnswerOption"(id,"questionId",label,text,"isCorrect","order") VALUES
  ('o1','q1','أ','الإقصاء',true,1),('o2','q1','ب','تكلفة الاستجابة',false,2);
INSERT INTO "File"(id,"originalName","mimeType","sizeBytes",sha256,"storageKey","uploadedById") VALUES ('f1','x.pdf','application/pdf',1,'h1','k1','u_admin');
INSERT INTO "Review"(id,target,"questionId","reviewerId",decision) VALUES ('r1','QUESTION','q1','u_admin','APPROVE');
INSERT INTO "AuditLog"(id,"actorId",action,entity,"entityId") VALUES ('al1','u_admin','question.publish','Question','q1');
INSERT INTO "UserExamTarget"(id,"userId","trackId") VALUES ('tg1','u_student','t_c');
INSERT INTO "Purchase"(id,"userId","targetId",product,"amountHalala","vatHalala",provider,"providerRef",status) VALUES ('p1','u_student','tg1','pass',10000,1500,'gw','ref1','paid');
INSERT INTO "UserConsent"(id,"userId",kind,"policyVersion",granted) VALUES ('cs1','u_student','PRIVACY_POLICY','v1',true);
INSERT INTO "ExamAttempt"(id,"userId",kind,config,"totalCount") VALUES ('at1','u_student','PRACTICE','{}',1);
INSERT INTO "UserAnswer"(id,"userId","questionId","questionVersion","attemptId","clientAnswerId","selectedOptionId","isCorrect","firstExposure") VALUES ('ua1','u_student','q1',1,'at1','c-uuid-1','o2',false,true);
INSERT INTO "WrongAnswer"("userId","familyId","entryReason") VALUES ('u_student','fam1','WRONG');
INSERT INTO "SrsReviewLog"(id,"userId","familyId","questionId","userAnswerId",rating,"stateBefore",due,stability,difficulty,"elapsedDays","scheduledDays") VALUES ('sl1','u_student','fam1','q1','ua1','AGAIN','NEW',now(),0,0,0,0);
INSERT INTO "QuestionReport"(id,"questionId","userId",reason) VALUES ('rp1','q1','u_student','UNCLEAR');
INSERT INTO "Bookmark"("userId","questionId",kind) VALUES ('u_student','q1','FAVORITE');

-- ---------- 1. PDPL erasure of a paying student is not blocked ----------
DELETE FROM "User" WHERE id='u_student';
DO $$ BEGIN
  IF (SELECT "userId" FROM "Purchase" WHERE id='p1') IS NOT NULL THEN RAISE EXCEPTION 'purchase not de-identified'; END IF;
  IF EXISTS (SELECT 1 FROM "UserAnswer" WHERE id='ua1') THEN RAISE EXCEPTION 'answers not erased'; END IF;
  IF EXISTS (SELECT 1 FROM "WrongAnswer") THEN RAISE EXCEPTION 'review cards not erased'; END IF;
  IF (SELECT "userId" FROM "QuestionReport" WHERE id='rp1') IS NOT NULL THEN RAISE EXCEPTION 'report not de-identified'; END IF;
  IF NOT EXISTS (SELECT 1 FROM "QuestionReport" WHERE id='rp1') THEN RAISE EXCEPTION 'QA trail lost'; END IF;
  RAISE NOTICE 'PASS 1: student erasure';
END $$;

-- ---------- 2. Erasing the founder/staff keeps the editorial trail ----------
DELETE FROM "User" WHERE id='u_admin';
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM "Review" WHERE id='r1' AND "reviewerId" IS NULL) THEN RAISE EXCEPTION 'review trail lost'; END IF;
  IF NOT EXISTS (SELECT 1 FROM "AuditLog" WHERE id='al1' AND "actorId" IS NULL) THEN RAISE EXCEPTION 'audit lost'; END IF;
  IF NOT EXISTS (SELECT 1 FROM "Question" WHERE id='q1' AND "createdById" IS NULL) THEN RAISE EXCEPTION 'question lost'; END IF;
  IF NOT EXISTS (SELECT 1 FROM "File" WHERE id='f1' AND "uploadedById" IS NULL) THEN RAISE EXCEPTION 'file lost'; END IF;
  RAISE NOTICE 'PASS 2: staff erasure';
END $$;

-- ---------- 3. A second correct option is rejected ----------
DO $$ BEGIN
  BEGIN
    UPDATE "AnswerOption" SET "isCorrect"=true WHERE id='o2';
    RAISE EXCEPTION 'FAIL: two correct options accepted';
  EXCEPTION WHEN unique_violation THEN RAISE NOTICE 'PASS 3: one correct option';
  END;
END $$;

-- ---------- 4. Publishing a recall-based key without a reference is rejected ----------
DO $$ BEGIN
  BEGIN
    INSERT INTO "ItemFamily"(id) VALUES ('fam2');
    INSERT INTO "Question"(id,"trackId","categoryId","topicId","familyId",stem,"stemNorm",origin,"answerBasis","answerConfidence",explanation,"explanationOrigin",status,"updatedAt")
    VALUES ('q2','t_c','c1','tp1','fam2','س','س','BASED_ON_RECALL','REFERENCE_VERIFIED','SINGLE_SOURCE','ش','TEAM_AUTHORED','PUBLISHED',now());
    RAISE EXCEPTION 'FAIL: published without reference';
  EXCEPTION WHEN check_violation THEN RAISE NOTICE 'PASS 4: publish gate';
  END;
END $$;

-- ---------- 5. A single-source key cannot be scorable ----------
DO $$ BEGIN
  BEGIN
    UPDATE "Question" SET "answerConfidence"='SINGLE_SOURCE' WHERE id='q1';
    RAISE EXCEPTION 'FAIL: scorable single-source key accepted';
  EXCEPTION WHEN check_violation THEN RAISE NOTICE 'PASS 5: scoring gate';
  END;
END $$;

-- ---------- 6. Question category must match its topic ----------
DO $$ BEGIN
  INSERT INTO "Category"(id,"trackId",code,"nameAr") VALUES ('c2','t_c','C2','أخرى');
  BEGIN
    UPDATE "Question" SET "categoryId"='c2' WHERE id='q1';
    RAISE EXCEPTION 'FAIL: category/topic mismatch accepted';
  EXCEPTION WHEN foreign_key_violation THEN RAISE NOTICE 'PASS 6: taxonomy consistency';
  END;
END $$;

-- ---------- 7. Answered questions cannot be hard-deleted ----------
DO $$ BEGIN
  INSERT INTO "User"(id,name,email,"updatedAt") VALUES ('u2','x','x@example.com',now());
  INSERT INTO "ExamAttempt"(id,"userId",kind,config,"totalCount") VALUES ('at2','u2','PRACTICE','{}',1);
  INSERT INTO "UserAnswer"(id,"userId","questionId","questionVersion","attemptId","clientAnswerId","selectedOptionId","isCorrect","firstExposure") VALUES ('ua2','u2','q1',1,'at2','c-uuid-2','o1',true,true);
  BEGIN
    DELETE FROM "Question" WHERE id='q1';
    RAISE EXCEPTION 'FAIL: answered question deleted';
  EXCEPTION WHEN foreign_key_violation THEN RAISE NOTICE 'PASS 7: no hard delete of answered questions';
  END;
END $$;

-- ---------- 8. Autosave retry is idempotent ----------
DO $$ BEGIN
  BEGIN
    INSERT INTO "UserAnswer"(id,"userId","questionId","questionVersion","attemptId","clientAnswerId","isCorrect","firstExposure") VALUES ('ua3','u2','q1',1,'at2','c-uuid-2',true,false);
    RAISE EXCEPTION 'FAIL: duplicate autosave accepted';
  EXCEPTION WHEN unique_violation THEN RAISE NOTICE 'PASS 8: idempotent autosave';
  END;
END $$;

-- ---------- 9. Arabic trigram search works ----------
DO $$ BEGIN
  IF similarity('الاقصاء', 'اقصاء') < 0.4 THEN RAISE EXCEPTION 'FAIL: trigram similarity on Arabic'; END IF;
  RAISE NOTICE 'PASS 9: Arabic trigrams';
END $$;

-- ---------- 10. search schema: text + fuzzy lookup on the normalized key ----------
DO $$ BEGIN
  INSERT INTO search.question_index(question_id, key_text) VALUES ('q1', 'طالب تحدث مع زميله فاخرجه المعلم من الفصل ما الاسلوب المستخدم اقصاء');
  IF NOT EXISTS (SELECT 1 FROM search.question_index WHERE tsv @@ plainto_tsquery('simple','اقصاء')) THEN
    RAISE EXCEPTION 'FAIL: tsvector lookup'; END IF;
  IF NOT EXISTS (SELECT 1 FROM search.question_index WHERE key_text % 'طالب تحدث مع زميله فاخرجه المعلم') THEN
    RAISE EXCEPTION 'FAIL: trigram lookup'; END IF;
  RAISE NOTICE 'PASS 10: search schema';
END $$;

ROLLBACK;
