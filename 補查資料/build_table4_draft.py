"""
表4 個別因素（項目 7–25）四個評價單元草稿 + 表3 各設施子欄位最近設施表（v2，依 Codex 第二輪審查修正）。
輸入（同目錄）：parcels_shulin.geojson、parcels_geometry.csv、ntpc_landmarks.json、ntpc_parking.json、osm_pois.json、osm_junctions.json、osm_roads_bbox.json
輸出：table4_draft.csv、table4_draft.md、facilities_nearest.csv
距離：EPSG:3826 直線距離（評價單元質心 → 設施點或 OSM 外接框中心）。表3 正式應改用區段中心點；通達型細項正式應改路線距離。
時點：價格日期 2022-09-01。捷運以路線營運白名單過濾；OSM start_date/opening_date 晚於價格日期者排除；名稱含「關閉」者排除。
"""
import json, csv, math, os, re
from shapely.geometry import shape
from shapely.ops import unary_union, transform
from pyproj import Transformer
HERE=os.path.dirname(os.path.abspath(__file__))
to3826=Transformer.from_crs("EPSG:4326","EPSG:3826",always_xy=True).transform
VALUATION="2022-09-01"
# 2022-09-01 已營運之捷運／輕軌路線（新北市境內）；萬大樹林線、三鶯線、安坑輕軌、汐止東湖線當時未通車
MRT_NOT_OPEN=("施工中","萬大樹林線","三鶯線","安坑輕軌","汐止東湖線")
POI_BBOX=(24.96,121.39,25.02,121.45); JN_BBOX=(24.93,121.36,25.05,121.48)

# ---- 評價單元（P003 合併） ----
gj=json.load(open(os.path.join(HERE,"parcels_shulin.geojson"),encoding="utf-8"))
geoms={}
for f in gj["features"]:
    key=f["properties"]["區段"].split()[0]; geoms.setdefault(key,[]).append(transform(to3826,shape(f["geometry"])))
units={k:unary_union(v) for k,v in geoms.items()}
order=["P001-00","P002-00","P003-00","P004-00"]
labels={"P001-00":"P001 比準地 樹德段1415","P002-00":"P002 樹德段284","P003-00":"P003 太平段367+917","P004-00":"P004 文林段317"}
cent={k:units[k].centroid for k in order}
def coverage(pt,bbox):
    """質心到查詢框各邊的最短距離（超過此距離的『最近設施』不保證是全域最近）"""
    s,w,n,e=bbox; xs=[to3826(w,s),to3826(e,s),to3826(e,n),to3826(w,n)]
    return min(pt.x-xs[0][0], xs[1][0]-pt.x, pt.y-xs[0][1], xs[2][1]-pt.y)
cov={k:coverage(cent[k],POI_BBOX) for k in order}; covj={k:coverage(cent[k],JN_BBOX) for k in order}

# ---- 設施 ----
fac=[]
def add_fac(cat,sub,name,x,y,source,extra=""): fac.append(dict(cat=cat,sub=sub,name=name,x=x,y=y,source=source,extra=extra))
lm=json.load(open(os.path.join(HERE,"ntpc_landmarks.json"),encoding="utf-8"))
SCHOOL={"國民小學":"國小","國民中學":"國中","完全中學":"高中","高中職":"高中","大專院校":"大專院校"}
SERVICE={"公所":"機關","戶政事務所":"機關","地政事務所":"機關","衛生所":"機關","地區醫院":"醫院","區域醫院":"醫院","醫學中心":"醫院","稅捐機關":"機關","監理機關":"機關"}
for r in lm:
    try: x=float(r["twd97_x"]); y=float(r["twd97_y"])
    except: continue
    if x==0 or y==0: continue
    t=r["地標類型"]; n=r["地標名稱"]; src=f'新北市重要地標 objectid={r.get("objectid")}'
    if t in SCHOOL: add_fac("學校",SCHOOL[t],n,x,y,src)
    elif t=="火車站": add_fac("車站","火車站",n,x,y,src)
    elif t=="捷運站":
        if any(k in n for k in MRT_NOT_OPEN): add_fac("捷運站(2022未營運)","捷運站(2022未營運)",n,x,y,src)
        else: add_fac("車站","捷運站",n,x,y,src)
    elif t in SERVICE: add_fac("服務性設施",SERVICE[t],n,x,y,src)
pk=json.load(open(os.path.join(HERE,"ntpc_parking.json"),encoding="utf-8"))
seen_pk=set()
for r in pk:
    if r.get("ID") in seen_pk: continue
    seen_pk.add(r.get("ID"))
    try: x=float(r["TW97X"]); y=float(r["TW97Y"])
    except: continue
    if x==0 or y==0: continue
    extra=f'{r.get("TOTALCAR","?")}車位；時段 {r.get("SERVICETIME","?")}；{(r.get("PAYEX") or "").replace(chr(10)," ")[:40]}'
    add_fac("停車場","路外停車場",r["NAME"],x,y,f'新北市路外公共停車場 ID={r.get("ID")}',extra)
osm=json.load(open(os.path.join(HERE,"osm_pois.json"),encoding="utf-8"))["elements"]
def osm_xy(e):
    if "lat" in e: return to3826(e["lon"],e["lat"])
    if "center" in e: return to3826(e["center"]["lon"],e["center"]["lat"])
def osm_name(e,t):
    return t.get("name") or t.get("name:zh") or t.get("branch") or t.get("ref") or t.get("operator") or f'(無名 {e["type"]}/{e["id"]})'
def later_than_valuation(t):
    for k in ("start_date","opening_date"):
        v=t.get(k,"")
        m=re.match(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?",v)
        if m:
            d=f"{m.group(1)}-{m.group(2) or '01'}-{m.group(3) or '01'}"
            if d>VALUATION: return True
    return False
for e in osm:
    t=e.get("tags",{}); xy=osm_xy(e)
    if not xy: continue
    n=osm_name(e,t); x,y=xy; src=f'OSM {e["type"]}/{e["id"]}'
    if later_than_valuation(t): add_fac("排除(價格日期後啟用)",t.get("amenity") or t.get("shop") or "",n,x,y,src,t.get("start_date") or t.get("opening_date")); continue
    if "關閉" in n or t.get("disused") or t.get("abandoned") or any(k.startswith("disused:") for k in t): add_fac("排除(已關閉)","",n,x,y,src); continue
    a,s_,l,pw,mm,rw,pl,lu=(t.get(k) for k in ("amenity","shop","leisure","power","man_made","railway","place","landuse"))
    if a=="marketplace": add_fac("市場","傳統市場",n,x,y,src)
    elif ("市場" in n or "夜市" in n) and not s_: add_fac("市場(名稱關鍵字待確認)",a or "",n,x,y,src)  # 不進表4
    if s_=="supermarket": add_fac("市場","超級市場",n,x,y,src)
    if s_ in ("mall","department_store"): add_fac("市場","超大型購物中心",n,x,y,src)
    if l=="park": add_fac("公園廣場","公園",n,x,y,src)
    if l=="garden" and t.get("garden:style")!="kitchen": add_fac("公園廣場","公園(garden,待確認)",n,x,y,src)
    if l=="playground" or pl=="square": add_fac("公園廣場","廣場/遊戲場",n,x,y,src)
    if a=="bus_station": add_fac("車站","客運站",n,x,y,src)
    if rw=="station": add_fac("車站(OSM核對)","railway=station",n,x,y,src)
    if lu=="cemetery" or a in ("grave_yard","crematorium") or any(k in n for k in ("公墓","納骨","生命紀念","殯儀","火葬")): add_fac("嫌惡設施","殯葬",n,x,y,src)
    if pw=="tower": add_fac("嫌惡設施","高壓鐵塔",n,x,y,src,t.get("voltage",""))
    if pw=="substation" or "變電所" in n: add_fac("嫌惡設施","變電所",n,x,y,src,f'{t.get("operator","")} {t.get("voltage","")}'.strip())
    if pw=="plant": add_fac("嫌惡設施(待確認)","發電設施",n,x,y,src,t.get("plant:source",""))
    if mm=="storage_tank": add_fac("嫌惡設施(待確認)","儲槽(內容物未知)",n,x,y,src,t.get("content",""))
    if mm=="wastewater_plant" or any(k in n for k in ("焚化","掩埋","污水","汙水")): add_fac("嫌惡設施","廢棄物處理",n,x,y,src)
    if a=="post_office": add_fac("服務性設施","郵局",n,x,y,src)
    if a=="bank": add_fac("服務性設施","銀行",n,x,y,src)
    if a=="parking": add_fac("停車場","OSM停車場",n,x,y,src)
    if "商圈" in n: add_fac("商圈","商圈",n,x,y,src)
jn=json.load(open(os.path.join(HERE,"osm_junctions.json"),encoding="utf-8"))["elements"]
for e in jn:
    t=e.get("tags",{}); xy=osm_xy(e)
    if not xy: continue
    add_fac("交流道","交流道(匝道)",f'{t.get("name") or "(無名匝道)"} {t.get("ref") or ""}'.strip(),xy[0],xy[1],f'OSM node/{e["id"]}')
# 同類同名 50m 內去重（例：家樂福 node 超市 + way 購物中心）
dedup=[]
for f in fac:
    dup=next((g for g in dedup if g["cat"]==f["cat"] and g["name"]==f["name"] and math.hypot(g["x"]-f["x"],g["y"]-f["y"])<=50),None)
    if dup: dup["sub"]=dup["sub"] if dup["sub"]==f["sub"] else f'{dup["sub"]}/{f["sub"]}'; continue
    dedup.append(f)
fac=dedup
# 面前道路類別：由 OSM 道路資料依名稱查
roads=json.load(open(os.path.join(HERE,"osm_roads_bbox.json"),encoding="utf-8"))["elements"]
road_cls={}
for e in roads:
    t=e.get("tags",{}); nm=t.get("name")
    if nm: road_cls.setdefault(nm,set()).add(t.get("highway","")+("/"+t["service"] if t.get("service") else ""))
CLS={"primary":"主要道路","trunk":"主要道路","secondary":"次要道路","tertiary":"次要道路"}
def road_kind(name):
    tags=sorted(road_cls.get(name,set())); kinds={CLS.get(tg.split("/")[0],"巷道") for tg in tags}
    return ("／".join(sorted(kinds)) or "待查")+f'（OSM {", ".join(tags) or "無此路名"}）'

def nearest(cat,pt,sub=None,k=1):
    c=sorted(((math.hypot(f["x"]-pt.x,f["y"]-pt.y),f) for f in fac if f["cat"]==cat and (not sub or sub in f["sub"].split("/"))),key=lambda z:z[0])
    return c[:k] if k>1 else (c[0] if c else None)

# ---- 級距（樹林區住宅用地個別因素基準 p.6–9，判級用原始量測值）----
def g_near(d):  return "優" if d<250 else "稍優" if d<500 else "普通" if d<1000 else "稍劣" if d<2000 else "劣"
def g_bad(d):   return "優" if d>=2000 else "稍優" if d>=1000 else "普通" if d>=500 else "稍劣" if d>=200 else "劣"
def g_area(a):  return "優" if a>=600 else "稍優" if a>=400 else "普通" if a>=200 else "稍劣" if a>50 else "劣（基準 50m² 端點重疊，待釐清）" if a==50 else "劣"
def g_width(w): return "優" if w>=20 else "稍優" if w>=15 else "普通" if w>=8 else "稍劣" if w>=4 else "劣"
def g_depth(d): return "優" if 14<=d<30 else "稍優" if 30<=d<40 else "普通" if (7<=d<14 or 40<=d<50) else "稍劣" if 50<=d<60 else "劣"
def fmt_len(v):  # 手冊：寬深四捨五入至整公尺，小於 1m 保留兩位
    return f"{v:.2f}" if v<1 else f"{int(math.floor(v+0.5))}"

geo={}
for r in csv.DictReader(open(os.path.join(HERE,"parcels_geometry.csv"),encoding="utf-8-sig")): geo[r["地號"]]=r
def geo_row(k): return geo[{"P001-00":"1415","P002-00":"284","P003-00":"367+917","P004-00":"317"}[k]]
front_road={"P001-00":("啟智街",24.6),"P002-00":("啟智街",32.0),"P003-00":("鎮前街367巷4弄",7.5),"P004-00":("潭興街",65.7)}
volume_raw={"P001-00":"260%","P002-00":"200%","P003-00":"260%","P004-00":"260%"}

rows=[]
def add(item,fn): rows.append((item,{k:fn(k) for k in order}))
def cell(b,grade_fn,k,cat_cov=None,note=""):
    if not b: return "查無（查詢範圍內）"
    d,f=b; over=f"（超出查詢範圍 {cat_cov:.0f}m，需擴查）" if cat_cov is not None and d>cat_cov else ""
    return f'{f["name"]} {d:.0f}m（{grade_fn(d)}）{over}{note}'.strip()

add("7 面積(M²)", lambda k: f'{float(geo_row(k)["面積_m2"]):.2f}（{g_area(float(geo_row(k)["面積_m2"]))}）※圖算值，待登記面積')
def wd(k):
    r=geo_row(k); s,l=float(r["外接矩形_短邊_m"]),float(r["外接矩形_長邊_m"]); road,fl=front_road[k]
    return (l,s) if fl>=0.8*l else (s,l)
add("8 寬度(M)", lambda k: f'{fmt_len(wd(k)[0])}（原值 {wd(k)[0]:.2f}，{g_width(wd(k)[0])}）※以{front_road[k][0]}為出入面，待確認')
add("9 深度(M)", lambda k: f'{fmt_len(wd(k)[1])}（原值 {wd(k)[1]:.2f}，{g_depth(wd(k)[1])}）')
add("10 形狀", lambda k: geo_row(k)["形狀判讀"]+"（待看圖）")
add("11 臨街情形", lambda k: geo_row(k)["臨街判讀(候選,8m門檻)"] if k!="P003-00" else geo["367"]["臨街判讀(候選,8m門檻)"]+"（以 367 為準；合併外邊界待覆核）")
add("12 地勢", lambda k: "平坦（表3 區段「極平坦堅硬」；宗地相對出入道路高低待現場）")
add("13 道路種類", lambda k: f'{road_kind(front_road[k][0])}：{front_road[k][0]}')
add("14 面前道路寬度", lambda k: f'{front_road[k][0]}：待量（OSM 無 width；主辦方口頭皆 ≤8m，仍可能落在普通／稍劣／劣）')
add("15 接近學校之程度", lambda k: cell(nearest("學校",cent[k]),g_near,k))
add("16 接近市場之程度", lambda k: cell(nearest("市場",cent[k]),g_near,k,cov[k]))
add("17 接近公園、廣場之程度", lambda k: cell(nearest("公園廣場",cent[k]),g_near,k,cov[k]))
add("18 接近車站之程度", lambda k: cell(nearest("車站",cent[k]),g_near,k))
def shq(k):
    b=nearest("商圈",cent[k])
    if b: return cell(b,g_near,k,cov[k],"※OSM 名稱含商圈，待人工確認")
    b=nearest("車站",cent[k],sub="火車站"); return f'尚未取得可用商圈範圍（經濟部盤點清冊待查）；參考點 {b[1]["name"]} {b[0]:.0f}m，非定稿'
add("19 接近商圈之程度", shq)
def bad(k):
    c=nearest("嫌惡設施",cent[k],k=6)
    if not c: return "查無（查詢範圍內）"
    d,f=c[0]; first=f'{f["sub"]}：{f["name"]}{("（"+f["extra"]+"）") if f["extra"] else ""} {d:.0f}m（{g_bad(d)}）'
    others=[f'{g["sub"]} {g["name"]} {dd:.0f}m' for dd,g in c[1:] if dd<500]
    return first+("；另 500m 內：" + "、".join(others) if others else "")+" ※需航照與 2022 狀態確認"
add("20 嫌惡設施(類型)", bad)
def park(k):
    b=nearest("停車場",cent[k],sub="路外停車場")
    if not b: return "查無"
    d,f=b; return f'最近路外停車場 {f["name"]} {d:.0f}m（{f["extra"]}）；等級優／普通／劣待人工，需臨停資格與路邊停車證據'
add("21 停車方便性", park)
add("22 使用分區", lambda k: "第一種住宅區（稍優：住宅區；P001 捷開區依變更前分區，主辦方口頭）")
add("23 建蔽率(%)", lambda k: "50%（稍劣：50% 以上未滿 60%）")
add("24 容積率(%)", lambda k: f'200%（表3 原值 {volume_raw[k]}；主辦方口頭：臨 8m 以下巷道一律 200%；個別因素依土地開發分析法，四者相同免試算）')
add("25 有無禁限建", lambda k: "無（優；表3）")
add("6 其他（無尾巷）", lambda k: "待確認（需查道路拓撲與現場；無＝優、有＝劣）")

with open(os.path.join(HERE,"table4_draft.csv"),"w",encoding="utf-8-sig",newline="") as fp:
    w=csv.writer(fp); w.writerow(["項目"]+[labels[k] for k in order]); [w.writerow([it]+[v[k] for k in order]) for it,v in rows]
md=["| 項目 | "+" | ".join(labels[k] for k in order)+" |","|---|"+"---|"*4]+["| "+it+" | "+" | ".join(v[k] for k in order)+" |" for it,v in rows]

SUBS=[("學校","國小"),("學校","國中"),("學校","高中"),("學校","大專院校"),("市場","傳統市場"),("市場","超級市場"),("市場","超大型購物中心"),
      ("公園廣場","公園"),("公園廣場","廣場/遊戲場"),("車站","火車站"),("車站","捷運站"),("車站","客運站"),("交流道","交流道(匝道)"),
      ("服務性設施","郵局"),("服務性設施","醫院"),("服務性設施","機關"),("服務性設施","銀行"),("停車場","路外停車場"),
      ("嫌惡設施","高壓鐵塔"),("嫌惡設施","變電所"),("嫌惡設施(待確認)","儲槽(內容物未知)"),("嫌惡設施","殯葬"),("嫌惡設施","廢棄物處理"),
      ("捷運站(2022未營運)","捷運站(2022未營運)"),("市場(名稱關鍵字待確認)",None),("排除(價格日期後啟用)",None)]
fr=[]; md2=["| 子欄位 | "+" | ".join(labels[k] for k in order)+" |","|---|"+"---|"*4]
for cat,sub in SUBS:
    cells=[]
    for k in order:
        b=nearest(cat,cent[k],sub=sub); c=covj[k] if cat=="交流道" else cov[k]
        if b:
            d,f=b; over="（超出查詢範圍）" if d>c else ""; ex=f'［{f["extra"]}］' if f["extra"] and cat.startswith("排除") else ""
            cells.append(f'{f["name"]}{ex} {d:.0f}m{over}'); fr.append([sub or cat,labels[k],f["name"],round(d),f["source"],f["extra"]])
        else: cells.append("查無（查詢範圍內）"); fr.append([sub or cat,labels[k],"",None,"",""])
    md2.append("| "+(sub or cat)+" | "+" | ".join(cells)+" |")
with open(os.path.join(HERE,"facilities_nearest.csv"),"w",encoding="utf-8-sig",newline="") as fp:
    w=csv.writer(fp); w.writerow(["子欄位","評價單元","最近設施","直線距離_m","來源","備註"]); w.writerows(fr)
open(os.path.join(HERE,"table4_draft.md"),"w",encoding="utf-8").write("\n".join(md)+"\n\n"+"\n".join(md2)+"\n")
print("\n".join(md)); print(); print("\n".join(md2))
print("\ncoverage m:",{k:round(v) for k,v in cov.items()},"| facilities:",len(fac),{c:sum(1 for f in fac if f["cat"]==c) for c in sorted({f["cat"] for f in fac})})
