import datetime as dt, io, json, os, shutil, sys, time, traceback, zlib
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import config as S, feed, gemini, images, voice, render, meta, facebook, publishing_state
from PIL import Image

# Capture console logs in memory so any failure writes its exact log tail to state/<show>_status.json
_LOG_BUF = io.StringIO()
class _Tee:
    def __init__(self, orig): self.orig = orig
    def write(self, s):
        self.orig.write(s)
        _LOG_BUF.write(s)
    def flush(self): self.orig.flush()
sys.stdout = _Tee(sys.stdout)
sys.stderr = _Tee(sys.stderr)

KEY = os.environ["SHOW_KEY"]; show = S.SHOWS[KEY]
TEST = os.getenv("TEST_MODE", "").lower() == "true"
VIDEO_ID = os.getenv("VIDEO_ID", "").strip()
publish_requested = (not TEST) and os.getenv("DO_UPLOAD", "true").lower() != "false"
do_publish_facebook = publish_requested and facebook.configured()
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
tmp = os.path.join(S.BASE, f"tmp_{KEY}"); out_dir = os.path.join(S.BASE, "output"); os.makedirs(tmp, exist_ok=True); os.makedirs(out_dir, exist_ok=True)

SOURCE_EP_NO, EP_NO, ep = "", "", None

try:
    print(f"== {show['en']} | Facebook publishing={do_publish_facebook} | test={TEST}")
    feed.record_status(KEY, "running", log_tail=_LOG_BUF.getvalue())

    print("1/7 find episode")
    pending_social = feed.find_pending_social(KEY) if not VIDEO_ID and publish_requested else None
    retrying_social = bool(pending_social)
    ep = feed.by_id(VIDEO_ID) if VIDEO_ID else (pending_social or feed.find_episode(KEY))
    if VIDEO_ID and ep and feed.show_key_for(ep["title"]) != KEY:
        print("   this video belongs to another show; skipping")
        feed.record_status(KEY, "skipped_other_show", vid=VIDEO_ID, log_tail=_LOG_BUF.getvalue())
        sys.exit(0)
    if not ep:
        print("   no new unseen full episode for this show right now")
        feed.record_status(KEY, "no_new_episode", log_tail=_LOG_BUF.getvalue())
        sys.exit(0)
    print("  ", ep["title"], "|", ep["url"])
    SOURCE_EP_NO, SOURCE_DATE = ep["episode"] or "?", ep["date"] or dt.datetime.now(IST).strftime("%d %b %Y")

    # The video is framed as a two-day-ahead prediction: metadata/on-screen target date and episode are +2.
    def next_target(source_ep, source_date):
        target_ep = str(int(source_ep) + 2) if str(source_ep).isdigit() else source_ep
        parsed = None
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try: parsed = dt.datetime.strptime(source_date, fmt); break
            except ValueError: pass
        target_date = (parsed + dt.timedelta(days=2)).strftime("%d %b %Y") if parsed else (dt.datetime.now(IST) + dt.timedelta(days=2)).strftime("%d %b %Y")
        return target_ep, target_date

    EP_NO, DATE = next_target(SOURCE_EP_NO, SOURCE_DATE)
    print(f"  source episode/date: {SOURCE_EP_NO} / {SOURCE_DATE}; two-day target: {EP_NO} / {DATE}")

    # Avoid regenerating an episode already completed or published to Facebook.
    if not VIDEO_ID and not retrying_social and feed.is_done(KEY, ep["id"], SOURCE_EP_NO):
        print(f"   episode {SOURCE_EP_NO} ({ep['id']}) already marked done in state; skipping")
        feed.record_status(KEY, "already_published", vid=ep["id"], episode=SOURCE_EP_NO, target_ep=EP_NO, log_tail=_LOG_BUF.getvalue())
        sys.exit(0)
    if not VIDEO_ID and not retrying_social and do_publish_facebook:
        if publishing_state.platform_status(KEY, ep["id"], "facebook") == "success":
            feed.mark_done(KEY, ep["id"], episode_no=SOURCE_EP_NO, target_ep=EP_NO)
            print("   Facebook publishing already succeeded for this episode; skipping duplicate")
            sys.exit(0)

    def hindi_date(d):   # on-screen text must be Devanagari (the font has no Latin letters)
        import re
        m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})[A-Za-z]*\s+(\d{4})", d or "")
        mon = {k: v for k, v in zip(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], S.HI_MONTHS)}
        return f"{m.group(1)} {mon.get(m.group(2).lower(), m.group(2))} {m.group(3)}" if m else (d or "")

    print("2/7 Gemini watches the episode")
    data = gemini.analyze(ep["url"], show["en"], SOURCE_EP_NO)
    thumbnail_reference = ""
    try:
        thumbnail_reference = gemini.describe_thumbnail(ep["id"])
    except gemini.ThumbnailAnalysisError as exc:
        print("   source thumbnail analysis unavailable; using episode scene prompts:", str(exc)[:240])
    scenes = [s for s in data.get("scenes", []) if s.get("narration")]
    if TEST: scenes = scenes[:3]
    if len(scenes) < 4 and not TEST: raise SystemExit(f"Gemini returned too few scenes ({len(scenes)})")
    n = len(scenes); hook_i = min(max(int(data.get("hook_scene", 0) or 0), 0), n - 1)
    pred = [str(x) for x in data.get("prediction", [])][:2] or ["शायद आगे कहानी में नया मोड़ आएगा।"]

    print("3/7 voice")
    segs = [{"tag": "hook", "lines": [data.get("hook") or scenes[0]["narration"]], "img": hook_i, "chip": "आज की कहानी", "name": "शुरुआत", "emo": scenes[hook_i].get("emotion", "tense")}]
    for i, s in enumerate(scenes):
        segs.append({"tag": f"s{i}", "lines": [s["narration"]], "img": i, "chip": f"दृश्य {i + 1}/{n}", "name": s.get("title") or f"दृश्य {i + 1}", "emo": s.get("emotion", "tense")})
    segs.append({"tag": "cliff", "lines": [data.get("cliffhanger") or scenes[-1]["narration"]], "img": n - 1, "chip": "एपिसोड का अंत", "name": "एपिसोड का अंत", "emo": "shock"})
    segs.append({"tag": "pred", "lines": ["अब परसों की बात, लेकिन सिर्फ़ अनुमान के तौर पर।"] + pred, "img": n, "chip": "अनुमान", "name": "परसों क्या हो सकता है (अनुमान)", "emo": "tense"})
    segs.append({"tag": "outro", "lines": ["पूरा एपिसोड आधिकारिक चैनल पर उपलब्ध है।", S.OUTRO_LINE], "img": 0, "chip": "धन्यवाद", "name": "", "emo": "happy"})
    voice.synth_all(segs, tmp)
    total = sum(s["times"][-1][1] for s in segs)
    print(f"   narration {total:.0f}s ({int(total // 60)}:{int(total % 60):02d})", "" if 100 <= total <= 200 else " <- outside the 2-3 min target")

    print("4/7 illustrations")
    seed = zlib.crc32(ep["id"].encode()) % 100000
    jobs = []   # (scene index, label, prompt)
    for i, sc in enumerate(scenes):
        jobs.append((i, "wide", sc["image_prompt"]))
        if S.IMAGES_PER_SCENE >= 2 and sc.get("closeup_prompt"): jobs.append((i, "close", sc["closeup_prompt"]))
    jobs.append((n, "wide", data.get("prediction_image_prompt") or scenes[-1]["image_prompt"] + ", mysterious mood, question mark in the air"))
    comps = {i: [] for i in range(n + 1)}; raws = {}
    for k, (i, label, p) in enumerate(jobs):
        raw, comp = f"{tmp}/img{i}_{label}.jpg", f"{tmp}/comp{i}_{label}.jpg"
        if images.generate(p, seed + (7 if label == "close" else 0), raw):
            render.cover(raw, comp)
            raws[(i, label)] = raw
        else:
            print(f"    image {i} {label}: generation failed; deferring fallback")
            continue
        comps[i].append(comp)

    generated_indices = {i for i, _ in raws}
    for i, source in images.reuse_nearest_generated_images(comps, generated_indices):
        print(f"    image {i}: reusing generated artwork from scene {source}")
    if not generated_indices:
        print("    no generated episode art available; using title cards")
        for i in range(n + 1):
            comp = f"{tmp}/comp{i}_fallback.jpg"
            render.card(
                scenes[min(i, n - 1)].get("title", ""),
                scenes[min(i, n - 1)].get("emotion", ""),
                comp,
            )
            comps[i].append(comp)

    pv = f"{out_dir}/{KEY}_{ep['id']}_preview"; os.makedirs(pv, exist_ok=True)
    for (i, label), raw in raws.items(): shutil.copy(raw, f"{pv}/image_{i + 1:02d}_{label}.jpg")
    json.dump({"prompts": [{"scene": i + 1, "type": lb, "prompt": p} for i, lb, p in jobs], "narration": [s["lines"] for s in segs]}, open(f"{pv}/script_and_prompts.json", "w"), ensure_ascii=False, indent=1)
    try:
        allc = [c for i in range(n + 1) for c in comps[i]]
        th = [Image.open(c).convert("RGB").resize((640, 360)) for c in allc]; cols = 3; rows = (len(th) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 640, rows * 360), (20, 20, 20))
        for i, t in enumerate(th): sheet.paste(t, ((i % cols) * 640, (i // cols) * 360))
        sheet.save(f"{pv}/contact_sheet.jpg", quality=85)
    except Exception as e: print("   contact sheet skipped:", e)

    print("5/7 render")
    files, starts, t0 = [], [], 0.0
    for k, s in enumerate(segs):
        f = f"{tmp}/seg_{s['tag']}.mp4"
        D = render.segment(s["tag"], f"{show['hi']} | परसों का एपिसोड {EP_NO}", s["chip"], s["emo"], s["lines"], s["times"], s["audio"], comps[s["img"]], tmp, f, t0, total, v0=k, word_times=s.get("word_times"))
        files.append(f)
        if s["name"]: starts.append((t0, s["name"]))
        t0 += D; print(f"   {s['tag']}: {D:.0f}s")
    name = f"{out_dir}/{KEY}_{ep['id']}"
    main_emo = (scenes[hook_i].get("emotion") if scenes else "tense") or "tense"
    music = render.auto_music(tmp, t0, emotion=main_emo)
    print(f"   music: automatic background music ({main_emo}) -> {os.path.basename(music)}")
    render.concat(files, tmp, name + ".mp4", music, t0, emotion=main_emo)

    print("6/7 thumbnail + metadata")
    thumb = name + ".jpg"
    thumbnail_prompt = (
        "Create a dramatic, polished 16:9 recap-video cover illustration. "
        f"Episode moment: {scenes[hook_i].get('image_prompt', '')}. "
        f"Emotional hook: {data.get('hook', '')}. "
        "Use expressive original fictional faces, strong separation between foreground and background, "
        "bright cinematic lighting, and clear space across the lower third for added Hindi title text. "
        "Do not draw any text, letters, logos, or watermarks."
    )
    if thumbnail_reference:
        thumbnail_prompt += (
            " Use only the broad composition and color balance from this episode-thumbnail description; "
            "do not reproduce its people, text, logo, or exact artwork: " + thumbnail_reference[:700]
        )
    thumbnail_art = f"{tmp}/thumbnail_art.jpg"
    if not images.generate_thumbnail(thumbnail_prompt, seed + 1001, thumbnail_art):
        print("   generated thumbnail art unavailable; using the existing episode illustration")
        thumbnail_art = raws.get((hook_i, "close")) or raws.get((hook_i, "wide")) or comps[hook_i][0]
    render.thumbnail(thumbnail_art, data.get("thumb_text") or data.get("headline") or "क्या होगा आगे?",
                      show["hi"], f"एपिसोड {EP_NO} | {hindi_date(DATE)}", thumb)
    kws = [str(k) for k in data.get("keywords", [])]
    title = meta.make_title(show, EP_NO, DATE, data.get("headline") or "", source_ep=SOURCE_EP_NO, source_date=SOURCE_DATE)
    tags = meta.make_tags(show, EP_NO, DATE, kws)
    desc = meta.make_description(show, EP_NO, DATE, ep["url"], data.get("hook", ""), starts, pred, kws, tags, source_ep=SOURCE_EP_NO, source_date=SOURCE_DATE)
    json.dump({"title": title, "description": desc, "tags": tags, "source": ep["url"], "seconds": round(t0)}, open(name + ".json", "w"), ensure_ascii=False, indent=2)
    print("   title:", title, "|", len(tags), "tags")

    print("7/7 Facebook publishing")
    social_issues = []
    if do_publish_facebook:
        replacements = {
            "{title}": title,
            "{description}": desc,
            "{show}": show["en"],
            "{episode}": str(EP_NO),
            "{hook}": str(data.get("hook") or ""),
        }

        def platform_caption(env_key, default):
            text = os.getenv(env_key) or default
            for placeholder, value in replacements.items():
                text = text.replace(placeholder, value)
            return text

        def platform_needs_publish(platform):
            if publishing_state.claim(KEY, ep["id"], platform, episode=SOURCE_EP_NO):
                return True
            status = publishing_state.platform_status(KEY, ep["id"], platform)
            if status == "success":
                print(f"   {platform} already succeeded for this episode; skipping duplicate publish")
                return False
            issue = f"{platform}: unresolved {status} attempt requires manual verification"
            social_issues.append(issue)
            print(f"   {issue}")
            return False

        if platform_needs_publish("facebook"):
            try:
                fb_id = facebook.publish_video(
                    name + ".mp4",
                    title=title,
                    description=platform_caption("FACEBOOK_DESCRIPTION", desc),
                    thumbnail_path=thumb,
                )
                publishing_state.update(KEY, ep["id"], "facebook", "success", episode=SOURCE_EP_NO, media_id=fb_id)
                feed.mark_done(KEY, ep["id"], episode_no=SOURCE_EP_NO, target_ep=EP_NO)
                print(f"   Facebook publishing succeeded: {fb_id}")
            except Exception as ex:
                status = "uncertain" if getattr(ex, "uncertain", False) else "failed"
                publishing_state.update(KEY, ep["id"], "facebook", status, episode=SOURCE_EP_NO, error=str(ex))
                social_issues.append(f"facebook {status}: {str(ex)[:200]}")
                print(f"   Facebook publishing {status}: {type(ex).__name__}: {str(ex)[:300]}")

    if not do_publish_facebook:
        feed.record_status(KEY, "rendered_no_upload", vid=ep["id"], episode=SOURCE_EP_NO, target_ep=EP_NO, log_tail=_LOG_BUF.getvalue())
    if social_issues:
        feed.record_status(
            KEY, "partial_success", vid=ep["id"], episode=SOURCE_EP_NO, target_ep=EP_NO,
            error="; ".join(social_issues), log_tail=_LOG_BUF.getvalue(),
        )
    print("done", name)

except SystemExit as se:
    if se.code not in (0, None):
        err_msg = str(se)
        print("FAILED:", err_msg)
        feed.record_status(
            KEY, "failed",
            vid=ep["id"] if ep else VIDEO_ID,
            episode=SOURCE_EP_NO,
            target_ep=EP_NO,
            error=err_msg,
            log_tail=_LOG_BUF.getvalue(),
        )
    raise
except Exception as ex:
    tb = traceback.format_exc()
    print("UNHANDLED ERROR:\n", tb)
    feed.record_status(
        KEY, "failed",
        vid=ep["id"] if ep else VIDEO_ID,
        episode=SOURCE_EP_NO,
        target_ep=EP_NO,
        error=f"{type(ex).__name__}: {ex}",
        log_tail=_LOG_BUF.getvalue(),
    )
    raise SystemExit(1)
