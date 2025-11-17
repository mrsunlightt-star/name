from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import os, time, json
import requests
from dotenv import load_dotenv
from zai import ZhipuAiClient
import re

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
os.makedirs("shared", exist_ok=True)
app.mount("/share", StaticFiles(directory="shared"), name="share")

RATE_LIMIT_STORE = {}
MEMBER_STORE = {}
LAST_UPSTREAM = {"status": None, "error": None}
BAIDU_TOKEN = {"value": None, "expires": 0}

def is_member(req: Request):
    v = req.headers.get("X-Member")
    if str(v).lower() in ("1","true","yes"):
        return True
    key = rate_limit_key(req)
    return MEMBER_STORE.get(key, False)

def rate_limit_key(req: Request):
    ip = req.headers.get("X-Forwarded-For") or req.client.host
    return ip

def can_request(req: Request):
    key = rate_limit_key(req)
    month = time.strftime("%Y-%m", time.localtime())
    store = RATE_LIMIT_STORE.setdefault(month, {})
    count = store.get(key, 0)
    if is_member(req):
        return True
    if count >= 2:
        return False
    return True

def increment_rate(req: Request):
    if is_member(req):
        return
    key = rate_limit_key(req)
    month = time.strftime("%Y-%m", time.localtime())
    store = RATE_LIMIT_STORE.setdefault(month, {})
    store[key] = store.get(key, 0) + 1

def zhipu_generate(payload: dict):
    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ZHIPU_API_KEY missing")
    client = ZhipuAiClient(api_key=api_key)
    # 仅保留必要字段，避免无关字段影响模型指令
    prefs = {
        "yourName": payload.get("yourName", ""),
        "genders": payload.get("genders", []),
        "styles": payload.get("styles", []),
        "count": payload.get("count", 2),
        "lang": payload.get("lang", "en")
    }
    target_lang = prefs.get("lang","en")
    user_content = (
        "根据用户偏好生成中文名字，严格返回 JSON 数组，每项包含："
        "name(中文全名，必须包含姓；姓1-2字，名1-2字，总长2-4)、"
        "pinyin(含姓氏的带声调拼音)、style、meaning、"
        "nameInsight(2-3句解读与寓意)、"
        "surnameInfo:{origin, meaning, story[50-150字的叙述，至少包含1位与该姓相关人物的最著名事迹]、figures[可选，1-2条人物简介]}。"
        "禁止返回发音提示，不得包含 pronounce_hint 字段。"
        "姓氏选择：从百家姓中随机选择并保持多样性，示例：李、王、张、刘、陈、杨、赵、黄、周、吴、徐、孙、朱、马、胡、郭、何、高、罗、郑、宋、谢、唐、曹、许、邹、魏、陶、姜、程、邓、韩、叶、梁、潘、金、钟、戴、任、袁、于、陆、石、洪、姚、邱、白、冯、彭、范、苏、杜、丁、贾、沈、田、侯、夏、方、熊、邵、曾、孟、秦、段、雷、霍、龚、卫、顾、蒲、欧阳、司马、上官、诸葛、东方、夏侯、尉迟、独孤、令狐、长孙、宇文、赫连、拓跋。"
        "不得与历史或政治人物的名字完全一致（可同姓，不得姓名完全一致）。"
        "多个候选的姓氏重复率需低于20%。"
        f"除 name 与 pinyin 外，其余文本字段请使用 {target_lang} 语言自然表达，准确可读。"
        "只返回纯JSON数组，不要任何说明文字或代码块。"
        f"输入偏好：{json.dumps(prefs, ensure_ascii=False)}"
    )
    try:
        resp = client.chat.completions.create(
            model="glm-4.5-flash",
            messages=[{"role":"system","content":"You are a helpful naming assistant."}, {"role":"user","content":user_content}],
            thinking={"type":"disabled"},
            stream=False,
            max_tokens=2048,
            temperature=0.6,
        )
        LAST_UPSTREAM["status"] = 200
        content = resp.choices[0].message.content
        if isinstance(content, list):
            parsed = content
        else:
            text = _extract_json_array(content)
            try:
                parsed = json.loads(text)
            except Exception:
                # second pass: remove potential invalid control chars
                text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)
                parsed = json.loads(text)
    except Exception as e:
        # 尝试安全降级：去除人物信息，仅生成基础字段，加入合规提醒
        LAST_UPSTREAM["error"] = str(e)[:400]
        try:
            safe_content = (
                "请生成合规的中文名字，严格返回 JSON 数组，每项包含："
                "name(中文全名，必须含姓；姓1-2字，名1-2字，总长2-4)、"
                "pinyin(含姓氏拼音)、style、meaning、nameInsight、"
                "surnameInfo:{origin, meaning, story[50-150字，必须包含1位人物的最著名事迹]、figures[可选] }。"
                "只返回纯JSON，避免敏感内容。"
                f"输入偏好：{json.dumps(prefs, ensure_ascii=False)}"
            )
            resp2 = client.chat.completions.create(
                model="glm-4.5-flash",
                messages=[{"role":"system","content":"You are a helpful naming assistant."}, {"role":"user","content":safe_content}],
                thinking={"type":"disabled"},
                stream=False,
                max_tokens=800,
                temperature=0.6,
            )
            LAST_UPSTREAM["status"] = 200
            content2 = resp2.choices[0].message.content
            text2 = _extract_json_array(content2)
            try:
                parsed = json.loads(text2)
            except Exception:
                text2 = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text2)
                parsed = json.loads(text2)
        except Exception as e2:
            LAST_UPSTREAM["error"] = (LAST_UPSTREAM["error"] or "") + " | safe_fallback:" + str(e2)[:300]
            parsed = []
    fallback_story = {
        "李":"李白：仗剑天涯，夜宿山寺写诗成绝唱，豪放飘逸，诗名传千古",
        "王":"王羲之：兰亭集会挥毫成序，书法千古流芳，世称书圣",
        "张":"张仲景：撰《伤寒论》体系医理，救济百姓，医道传承不绝",
        "刘":"刘备：三顾茅庐礼贤下士，兴复汉室，仁义立身",
        "林":"林则徐：虎门销烟严禁鸦片，开眼看世界，近代维新先声",
    }
    normalized = []
    for item in parsed:
        item.pop("pronounce_hint", None)
        si = item.get("surnameInfo") or {}
        story = si.get("story")
        if not story:
            surname = item.get("name", "")[0] if item.get("name") else ""
            story = fallback_story.get(surname, "该姓人物故事暂缺")
        # 裁剪到 150 字以内
        story = str(story)[:150]
        si["story"] = story
        # nameInsight 兜底
        if not item.get("nameInsight"):
            nm = item.get("name","")
            style = item.get("style","")
            meaning = item.get("meaning","")
            item["nameInsight"] = f"该名由姓与名组成，整体风格偏{style}。寓意：{meaning}。"
        item["surnameInfo"] = si
        normalized.append(item)
    banned = {"李白","王羲之","张仲景","刘备","林则徐","孔子","孟子","屈原","杜甫","苏轼","陶渊明","白居易"}
    compound = {"欧阳","司马","上官","诸葛","东方","夏侯","尉迟","独孤","令狐","长孙","宇文","赫连","拓跋"}
    def get_surname(n):
        if not n:
            return ""
        for s in compound:
            if n.startswith(s):
                return s
        return n[0]
    total = len(normalized)
    max_per = max(0, int(total*0.2))
    counts = {}
    out = []
    for it in normalized:
        nm = it.get("name","")
        if nm in banned:
            continue
        sn = get_surname(nm)
        c = counts.get(sn,0)
        if c >= max_per:
            continue
        counts[sn] = c+1
        out.append(it)
    normalized = out
    # Translation to target language (except name and pinyin)
    lang = prefs.get("lang", "en")
    if lang and lang != "zh":
        try:
            trans_prompt = (
                "Translate the following JSON into " + lang + ". "
                "Preserve fields 'name' and 'pinyin' as original. Translate textual fields: 'style', 'meaning', 'nameInsight', 'surnameInfo.origin', 'surnameInfo.meaning', 'surnameInfo.story'. "
                "Keep structure unchanged and natural, accurate, readable, not machine-like. Return pure JSON only. Input: " + json.dumps(normalized, ensure_ascii=False)
            )
            resp_t = client.chat.completions.create(
                model="glm-4.5-flash",
                messages=[{"role":"system","content":"You are a professional translator."}, {"role":"user","content":trans_prompt}],
                thinking={"type":"disabled"},
                stream=False,
                max_tokens=1800,
                temperature=0.2,
            )
            content_t = resp_t.choices[0].message.content
            text_t = _extract_json_array(content_t)
            translated = json.loads(text_t)
            return translated
        except Exception:
            return normalized
    return normalized

@app.post("/api/zhipu/generate")
async def api_generate(req: Request):
    if not can_request(req):
        raise HTTPException(status_code=429, detail="daily limit reached")
    payload = await req.json()
    try:
        result = zhipu_generate(payload)
        increment_rate(req)
    except HTTPException as e:
        raise e
    except Exception:
        raise HTTPException(status_code=502, detail="generation failed")
    return JSONResponse(result)

@app.get("/api/debug/status")
async def debug_status(req: Request):
    key_present = bool(os.environ.get("ZHIPU_API_KEY"))
    key = rate_limit_key(req)
    day = time.strftime("%Y-%m-%d", time.localtime())
    used = RATE_LIMIT_STORE.get(day, {}).get(key, 0)
    return {
        "has_api_key": key_present,
        "member": is_member(req),
        "used_today": used,
        "limit_per_day": 2,
        "last_upstream_status": LAST_UPSTREAM["status"],
        "last_error_snippet": LAST_UPSTREAM["error"],
    }

@app.get("/api/debug/ping")
async def debug_ping():
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    try:
        r = requests.get(url, timeout=8)
        return {"reachable": True, "status": r.status_code}
    except Exception as e:
        return {"reachable": False, "error": str(e)}

@app.get("/api/member/status")
async def member_status(req: Request):
    return {"member": is_member(req)}

@app.post("/api/member/activate")
async def member_activate(req: Request):
    key = rate_limit_key(req)
    payload = await req.json()
    sub_id = payload.get("subscription_id")
    if not sub_id:
        raise HTTPException(status_code=400, detail="subscription_id required")
    MEMBER_STORE[key] = True
    return {"ok": True}

@app.get("/api/paypal/config")
async def paypal_config():
    client_id = os.environ.get("PAYPAL_CLIENT_ID")
    plan_id = os.environ.get("PAYPAL_PLAN_ID")
    if not client_id or not plan_id:
        return {"enabled": False}
    return {"enabled": True, "client_id": client_id, "plan_id": plan_id}

@app.post("/api/subscription/checkout")
async def subscription_checkout():
    provider = os.environ.get("PAY_PROVIDER", "lemon")
    if provider not in ("lemon","paddle"):
        provider = "lemon"
    raise HTTPException(status_code=501, detail=f"checkout not configured for {provider}")

@app.post("/api/tts")
async def tts(req: Request):
    provider = req.query_params.get("provider", "browser")
    if provider != "baidu":
        raise HTTPException(status_code=400, detail="only baidu configured")
    body = await req.json()
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    # enforce pinyin-only to control cost
    if not re.match(r"^[\u4e00-\u9fa5·]{1,6}$", text):
        raise HTTPException(status_code=400, detail="only_chinese_name_allowed")
    api_key = os.environ.get("BAIDU_API_KEY")
    secret_key = os.environ.get("BAIDU_SECRET_KEY")
    if not api_key or not secret_key:
        raise HTTPException(status_code=500, detail="baidu config missing")
    now = time.time()
    if not BAIDU_TOKEN["value"] or now >= BAIDU_TOKEN["expires"]:
        r = requests.get("https://aip.baidubce.com/oauth/2.0/token", params={"grant_type":"client_credentials","client_id":api_key,"client_secret":secret_key}, timeout=20)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="baidu token error")
        j = r.json()
        BAIDU_TOKEN["value"] = j.get("access_token")
        BAIDU_TOKEN["expires"] = now + int(j.get("expires_in", 2592000)) - 60
    spd_raw = int(body.get("spd", 4))
    per_raw = int(body.get("per", 0))
    spd = max(0, min(9, spd_raw))
    per = per_raw if per_raw in (0,1,3,4) else 4
    params = {
        "tex": text,
        "tok": BAIDU_TOKEN["value"],
        "cuid": "web-client",
        "ctp": 1,
        "lan": "zh",
        "spd": spd,
        "pit": 5,
        "per": per,
        "aue": 3
    }
    r = requests.post("https://tsn.baidu.com/text2audio", data=params, timeout=30)
    ct = r.headers.get("Content-Type", "")
    if "audio" in ct:
        return Response(content=r.content, media_type=ct)
    return JSONResponse(status_code=502, content={"error":"tts_failed","detail":r.text[:200]})

@app.post("/api/share/upload")
async def share_upload(req: Request):
    form = await req.form()
    file = form.get("file")
    title = form.get("title")
    if not file:
        raise HTTPException(status_code=400, detail="file required")
    name = str(int(time.time()*1000)) + ".png"
    path = os.path.join("shared", name)
    try:
        with open(path, "wb") as f:
            f.write(await file.read())
    except Exception:
        raise HTTPException(status_code=500, detail="save_failed")
    url = f"http://localhost:8000/share/{name}"
    return {"url": url, "title": title or ""}
def _extract_json_array(text: str) -> str:
    s = str(text or "").strip()
    if s.startswith("```"):
        i1 = s.find("["); i2 = s.rfind("]")
        if i1 != -1 and i2 != -1:
            s = s[i1:i2+1]
    if not (s.startswith("[") and s.endswith("]")):
        m = re.search(r"\[[\s\S]*\]", s)
        if m: s = m.group(0)
    # normalize smart quotes and trailing commas
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    s = re.sub(r",\s*\]", "]", s)
    s = re.sub(r",\s*\}", "}", s)
    return s
@app.post("/api/share/upload")
async def share_upload(req: Request):
    if not is_member(req):
        raise HTTPException(status_code=403, detail="members only")
    form = await req.form()
    file = form.get("file")
    title = form.get("title")
    if not file:
        raise HTTPException(status_code=400, detail="file required")
    name = str(int(time.time()*1000)) + ".png"
    path = os.path.join("shared", name)
    try:
        with open(path, "wb") as f:
            f.write(await file.read())
    except Exception:
        raise HTTPException(status_code=500, detail="save_failed")
    url = f"http://localhost:8000/share/{name}"
    return {"url": url, "title": title or ""}