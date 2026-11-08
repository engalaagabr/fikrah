# ربط الباك إند (لعلاء ولأي حد هيوصّل الـAPI)

التطبيق بيكلّم الذكاء الاصطناعي من خلال **interface-ين بس**. الشاشات مش بتعرف إذا الشغل demo ولا API حقيقي، فلما نوصّل الباك إند مش المفروض نلمس أي شاشة.

| الـinterface | الملف | بيعمل إيه | النسخة التجريبية |
|---|---|---|---|
| `AiService.analyze(note, projectNotes)` | `lib/data/ai/ai_service.dart` | بعد حفظ النوت: تفريغ صوت / استخراج PDF، عنوان، مفاهيم، cluster، روابط، اقتراح صياغة | `DemoAiService` |
| `AiService.ask(question, projectNotes)` | نفس الملف | إجابة من نوتس المشروع بس + IDs المصادر | `DemoAiService` |
| `AttachmentUploader.upload(...)` | نفس الملف | رفع الملف مع progress من 0 لـ1 | `DemoUploader` |

## خطوات التوصيل
1. اعمل `lib/data/api/api_ai_service.dart` فيه `class ApiAiService implements AiService`، و`api_uploader.dart` فيه `ApiUploader`.
2. الـrequest/response DTOs تتحط جنب الـclient في `lib/data/api/dto/`. **متبعتش `Note` كامل:** هو صف من الداتابيز وفيه مسارات ملفات محلية والنص المقترح. ابعت اللي السيرفر محتاجه بس.
3. في `lib/app/providers.dart`، حط الـimplementations الجديدة مكان الـ`throw UnimplementedError` في `aiServiceProvider` و`uploaderProvider` تحت `AppMode.connected`.
4. شغّل كده:
   ```bash
   flutter run --dart-define=FIKRA_MODE=connected
   ```
   أي قيمة غير `demo` و`connected` بتفشل على طول من أول ما التطبيق يفتح.

## معنى الـresponse (`NoteInsights`)
- `title`: بيتحط **بس لو** المستخدم ساب العنوان فاضي. لو المستخدم كتب عنوان، عنوانه هو اللي بيفضل.
- `extractedText`: التفريغ أو النص المستخرج. `null` معناها "مفيش"، مش "سيبه زي ما هو".
- `proposedText`: اقتراح إعادة صياغة. بيتعرض للمستخدم بس لو هو ما عدّلش النوت وقت ما الـAI كان شغال. `null` معناها مفيش اقتراح.
- `concepts`: أقصى 8 بيتحفظوا. `cluster`: اسم المجموعة اللي النوت بتظهر فيها في الجراف.
- `links`: كل لينك `targetId` + `label` + `strength`.
  - التطبيق بيرفض أي target من مشروع تاني، أو نوت مش موجودة، أو النوت نفسها، أو مكرر.
  - الـstrength بيتحط بين 0 و1.
  - النوت بتملك الروابط **الخارجة** منها بس، وأي تحليل جديد بيبدّلها.

كل ده متطبق في `NotesRepository.applyInsights` في `lib/data/repositories.dart`، وفيه تيستات.

## الـIDs
- كل الـIDs (نوت، مشروع، لينك) UUID v4 بيتعمل على الموبايل (`lib/data/ids.dart`).
- السيرفر يقدر يستخدمهم كـidempotency keys: نفس `note.id` + نفس المحتوى = نفس الشغل.

## الوقت والفشل
- `NoteProcessor` (`lib/data/processing/note_processor.dart`) بيشغّل التحليل واحد ورا التاني، وبحد أقصى 90 ثانية.
- لو حصل exception أو timeout، النوت بتبقى `failed` والمستخدم يقدر يعمل retry. النوت نفسها عمرها ما بتضيع.
- لو التطبيق اتقفل وسط التحليل، بيكمّل لوحده أول ما يفتح.
- لسه ناقص قبل الربط (`docs/before-backend-and-release.md`): attempt id، retry/backoff، رفع الملف كـjob بيرجّع `attachmentId`، وتخزين الـtokens في Keystore.

## أمثلة نتفق عليها
قبل الكود محتاجين نكتب مع بعض مثال JSON لكل واحدة:
- request/response للنوت النصية
- request/response للنوت الصوتية (ازاي التسجيل يوصل)
- request/response للـPDF
- `ask`، وفيها شكل "ملقيناش إجابة"
