"""
宗地幾何計算（純標準函式庫，不需 shapely/pyproj）。
輸入：twland_raw.json（twland.ronny.tw 回傳的 GeoJSON）、osm_roads_bbox.json（Overpass highway ways）
輸出：parcels_shulin.geojson、parcels_geometry.csv、stdout 的 Markdown 表
量測：以各宗地中心點緯度的橢球「每度公尺數」做局部平面投影；宗地尺度誤差 < 0.1%。
"""
import json, math, csv, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROAD_TAGS = {"motorway","trunk","primary","secondary","tertiary","unclassified","residential",
             "living_street","service","road","pedestrian",
             "motorway_link","trunk_link","primary_link","secondary_link","tertiary_link"}
ROAD_CLASS = {"primary":"主要道路","primary_link":"主要道路","trunk":"主要道路","trunk_link":"主要道路",
              "secondary":"次要道路","secondary_link":"次要道路","tertiary":"次要道路","tertiary_link":"次要道路",
              "residential":"巷道","unclassified":"巷道","living_street":"巷道","service":"巷道","road":"巷道","pedestrian":"巷道"}
FRONT_THRESH_M = 8.0   # 宗地邊樣點到 OSM 道路中心線 ≤ 8m 視為「臨路候選」。只表示接近中心線，不代表可出入；P003 改 6m 即無候選
NEAR_REPORT_M = 25.0   # 25m 內的道路都列出供人工判讀

PARCELS = [  # 區段, 段, 地號(twland 內部編碼 = 地號*10000)
    ("P001-00 比準地", "樹德段", 14150000),
    ("P002-00 比較1", "樹德段", 2840000),
    ("P003-00 比較2", "太平段", 3670000),
    ("P003-00 比較2", "太平段", 9170000),
    ("P004-00 比較3", "文林段", 3170000),
]

def mpd(lat):
    p = math.radians(lat)
    mlat = 111132.954 - 559.822*math.cos(2*p) + 1.175*math.cos(4*p)
    mlon = 111412.84*math.cos(p) - 93.5*math.cos(3*p) + 0.118*math.cos(5*p)
    return mlat, mlon

def project(ring, lon0, lat0):
    mlat, mlon = mpd(lat0)
    return [((x-lon0)*mlon, (y-lat0)*mlat) for x, y in ring]

def shoelace(pts):
    a = 0.0
    for i in range(len(pts)-1):
        a += pts[i][0]*pts[i+1][1] - pts[i+1][0]*pts[i][1]
    return a/2.0

def centroid_ll(ring):
    # 先用平均點當投影原點，再以面積加權質心修正
    lon0 = sum(p[0] for p in ring)/len(ring); lat0 = sum(p[1] for p in ring)/len(ring)
    pts = project(ring, lon0, lat0)
    A = shoelace(pts); cx = cy = 0.0
    for i in range(len(pts)-1):
        cr = pts[i][0]*pts[i+1][1] - pts[i+1][0]*pts[i][1]
        cx += (pts[i][0]+pts[i+1][0])*cr; cy += (pts[i][1]+pts[i+1][1])*cr
    cx /= (6*A); cy /= (6*A)
    mlat, mlon = mpd(lat0)
    return lon0 + cx/mlon, lat0 + cy/mlat

def convex_hull(pts):
    pts = sorted(set(pts))
    if len(pts) <= 2: return pts
    def cross(o,a,b): return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    lower=[]; 
    for p in pts:
        while len(lower)>=2 and cross(lower[-2],lower[-1],p)<=0: lower.pop()
        lower.append(p)
    upper=[]
    for p in reversed(pts):
        while len(upper)>=2 and cross(upper[-2],upper[-1],p)<=0: upper.pop()
        upper.append(p)
    return lower[:-1]+upper[:-1]

def min_rect(pts):
    hull = convex_hull(pts); best=None
    for i in range(len(hull)):
        x1,y1 = hull[i]; x2,y2 = hull[(i+1)%len(hull)]
        th = math.atan2(y2-y1, x2-x1); c, s = math.cos(-th), math.sin(-th)
        rot = [(x*c - y*s, x*s + y*c) for x,y in hull]
        xs=[p[0] for p in rot]; ys=[p[1] for p in rot]
        w = max(xs)-min(xs); h = max(ys)-min(ys)
        if best is None or w*h < best[0]: best=(w*h, w, h, math.degrees(th))
    return best

def seg_dist(p, a, b):
    ax,ay=a; bx,by=b; px,py=p
    dx,dy = bx-ax, by-ay; L2 = dx*dx+dy*dy
    t = 0 if L2==0 else max(0,min(1,((px-ax)*dx+(py-ay)*dy)/L2))
    qx,qy = ax+t*dx, ay+t*dy
    return math.hypot(px-qx, py-qy)

def load_roads():
    p = os.path.join(HERE, "osm_roads_bbox.json")
    if not os.path.exists(p): return []
    d = json.load(open(p, encoding="utf-8"))
    roads=[]
    for e in d.get("elements", []):
        t = e.get("tags", {}); hw = t.get("highway")
        if hw not in ROAD_TAGS or "geometry" not in e: continue
        roads.append({"id": e["id"], "name": t.get("name",""), "highway": hw, "width": t.get("width",""),
                      "lanes": t.get("lanes",""), "geom": [(g["lon"], g["lat"]) for g in e["geometry"]]})
    return roads

def edge_roads(ring_ll, lon0, lat0, roads):
    """每條宗地邊 → 最近道路（名稱、類別、距離），並判斷是否臨路"""
    pts = project(ring_ll, lon0, lat0); out=[]
    for i in range(len(pts)-1):
        a, b = pts[i], pts[i+1]
        elen = math.hypot(b[0]-a[0], b[1]-a[1])
        samples = [(a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t) for t in (0.25,0.5,0.75)]
        best=None
        for r in roads:
            rg = project(r["geom"], lon0, lat0)
            d = min(seg_dist(s, rg[j], rg[j+1]) for s in samples for j in range(len(rg)-1)) if len(rg)>1 else 1e9
            if best is None or d < best[0]: best=(d, r)
        out.append({"edge": i, "length_m": round(elen,2),
                    "nearest_road": best[1]["name"] if best else "", "highway": best[1]["highway"] if best else "",
                    "width_tag": best[1]["width"] if best else "", "dist_m": round(best[0],2) if best else None,
                    "fronting": bool(best and best[0] <= FRONT_THRESH_M)})
    return out

def main():
    raw = json.load(open(os.path.join(HERE,"twland_raw.json"), encoding="utf-8"))
    roads = load_roads()
    feats=[]; rows=[]
    for label, sect, code in PARCELS:
        f = next(x for x in raw["features"] if x["properties"].get("鄉鎮")=="樹林區"
                 and x["properties"].get("地段")==sect and x["properties"].get("地號")==code)
        polys = f["geometry"]["coordinates"]  # MultiPolygon: [ [exterior, hole, ...], ... ]
        ring = [tuple(p) for p in polys[0][0]]
        if len(polys) > 1: print(f"[warn] {label} {sect} {code//10000} 有 {len(polys)} 個多邊形；面積為全部外環減內洞，中心點與臨路只用第一個外環", file=sys.stderr)
        clon, clat = centroid_ll(ring)
        area = 0.0; allpts = []
        for poly in polys:
            for k, r in enumerate(poly):
                rp = project([tuple(q) for q in r], clon, clat)
                a = abs(shoelace(rp)); area += -a if k else a
                if k == 0: allpts += rp
        pts = project(ring, clon, clat)
        _, w, h, ang = min_rect(allpts)
        short, long_ = (w, h) if w <= h else (h, w)
        rect = area/(w*h) if w*h else 0
        er = edge_roads(ring, clon, clat, roads) if roads else []
        front = [e for e in er if e["fronting"]]
        sens = {t: len({e["nearest_road"] for e in er if e["dist_m"] is not None and e["dist_m"] <= t}) for t in (6, 8, 10)}
        front_roads = {}
        for e in front: front_roads.setdefault(e["nearest_road"] or f'(無名, {e["highway"]})', 0.0); front_roads[e["nearest_road"] or f'(無名, {e["highway"]})'] += e["length_m"]
        near = sorted({(e["nearest_road"] or "(無名)", e["highway"], e["dist_m"]) for e in er if e["dist_m"] is not None and e["dist_m"] <= NEAR_REPORT_M}, key=lambda x: x[2])
        frontage_len = sum(front_roads.values())
        depth_by_area = area/frontage_len if frontage_len else None
        n_front = len(front_roads)
        street = {0:"未臨街地候選",1:"單面臨街候選",2:"兩條路名（路角地或雙面，待看圖）"}.get(n_front, "三條以上路名（待看圖）")
        shape = ("畸零地（面積<10m²）" if area < 10 else
                 "方形／梯形（矩形度≥0.85）" if rect >= 0.85 else ("長條形" if long_/max(short,0.01) >= 4 else "不規則形（矩形度<0.85）"))
        # TWD97 TM2 近似：以 twland 給的中心點不轉換，另附 WGS84；正式 TM2 轉換留給 pyproj
        row = {"區段": label, "地段": sect, "地號": code//10000,
               "面積_m2": round(area,2), "外接矩形_短邊_m": round(short,2), "外接矩形_長邊_m": round(long_,2),
               "矩形度": round(rect,3), "形狀判讀": shape,
               "臨路邊數": len(front), "臨路道路數": n_front, "臨街判讀(候選,8m門檻)": street,
               "臨路道路(8m門檻)": "；".join(f"{k} {v:.1f}m" for k,v in front_roads.items()),
               "臨路道路數@6m/8m/10m": f"{sens[6]}/{sens[8]}/{sens[10]}",
               "臨路總長_m": round(frontage_len,2),
               "25m內道路(名稱/類別/距中心線m)": "；".join(f"{n}/{ROAD_CLASS.get(h,h)}/{d}" for n,h,d in near),
               "中心點_lon": round(clon,6), "中心點_lat": round(clat,6), "頂點數": len(ring)-1,
               "來源": "twland.ronny.tw（easymap 2015 地籍）＋ OSM Overpass 2026-09-12"}
        rows.append(row)
        feats.append({"type":"Feature","geometry":f["geometry"],"properties":{**row, "edges": er}})
    # P003 兩筆合併
    p3 = [r for r in rows if r["區段"].startswith("P003")]
    if len(p3)==2:
        merged = {"區段":"P003-00 合併(367+917)","地段":"太平段","地號":"367+917","面積_m2": round(sum(r["面積_m2"] for r in p3),2),
                  "來源":"兩筆面積相加；寬深需合併多邊形後另算"}
        try:
            from shapely.geometry import shape as _shape
            from shapely.ops import unary_union, transform as _tf
            from pyproj import Transformer
            tr = Transformer.from_crs("EPSG:4326","EPSG:3826",always_xy=True).transform
            back = Transformer.from_crs("EPSG:3826","EPSG:4326",always_xy=True).transform
            geoms = [_tf(tr,_shape(x["geometry"])) for x in raw["features"] if x["properties"].get("鄉鎮")=="樹林區" and x["properties"].get("地段")=="太平段" and x["properties"].get("地號") in (3670000,9170000)]
            u = unary_union(geoms); mrr = u.minimum_rotated_rectangle; xs, ys = mrr.exterior.coords.xy
            sides = sorted({round(math.hypot(xs[i+1]-xs[i], ys[i+1]-ys[i]),2) for i in range(4)}); c = u.centroid; lon, lat = back(c.x, c.y)
            merged.update({"面積_m2": round(u.area,2), "外接矩形_短邊_m": sides[0], "外接矩形_長邊_m": sides[-1], "矩形度": round(u.area/mrr.area,3),
                           "形狀判讀": "方形／梯形（矩形度≥0.85）" if u.area/mrr.area>=0.85 else "不規則形（矩形度<0.85）",
                           "中心點_lon": round(lon,6), "中心點_lat": round(lat,6), "來源": "shapely unary_union（EPSG:3826）合併兩筆共邊多邊形"})
        except ImportError:
            merged["來源"] += "（需 shapely+pyproj 才能合併幾何）"
        rows.append(merged)
    with open(os.path.join(HERE,"parcels_shulin.geojson"),"w",encoding="utf-8") as fp:
        json.dump({"type":"FeatureCollection","features":feats}, fp, ensure_ascii=False, indent=1)
    keys = list(rows[0].keys())
    with open(os.path.join(HERE,"parcels_geometry.csv"),"w",encoding="utf-8-sig",newline="") as fp:
        wtr = csv.DictWriter(fp, fieldnames=keys); wtr.writeheader(); [wtr.writerow({k:r.get(k,"") for k in keys}) for r in rows]
    cols = ["區段","地段","地號","面積_m2","外接矩形_短邊_m","外接矩形_長邊_m","矩形度","形狀判讀","臨路道路數","臨街判讀(候選,8m門檻)","臨路道路(8m門檻)","臨路道路數@6m/8m/10m"]
    print("| " + " | ".join(cols) + " |"); print("|" + "---|"*len(cols))
    for r in rows: print("| " + " | ".join(str(r.get(c,"")) for c in cols) + " |")
    print(f"\nroads loaded: {len(roads)}")

if __name__ == "__main__": main()
