# 補查資料｜樹林區 P001–P004 資料蒐集工作區

對應 [../資料來源盤點-樹林區補查欄位.md](../資料來源盤點-樹林區補查欄位.md)（規劃、來源清單、判讀說明、Codex 審查全文）。這裡只放資料、程式與怎麼跑。

## 環境

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r 補查資料/requirements.txt      # shapely、pyproj、openpyxl
```

`compute_parcel_geometry.py` 只用標準函式庫；`build_table4_draft.py` 需要 shapely 與 pyproj（已驗證 Shapely 2.1.2、pyproj 3.8.0、Python 3.13）。

## 檔案

| 檔案 | 是什麼 | 來源／產生方式 |
|---|---|---|
| `twland_raw.json` | 5 筆地號的地籍多邊形（GeoJSON，WGS84） | twland.ronny.tw（easymap 2015 年以前地籍鏡像）；含蘆洲區同名段，程式已用鄉鎮過濾 |
| `osm_roads_bbox.json` | OSM 道路（bbox 24.978–25.003, 121.409–121.430） | Overpass，2026-09-12 |
| `osm_pois.json` | OSM 設施點（超市、市場、公園、墓地、鐵塔、變電所、郵局、銀行、停車場等；bbox 24.96–25.02, 121.39–121.45） | Overpass，2026-09-12 |
| `osm_junctions.json` | OSM 交流道匝道點（bbox 24.93–25.05, 121.36–121.48） | Overpass，2026-09-12 |
| `ntpc_landmarks.json` | 新北市重要地標全市 2,056 筆（學校、火車站、捷運站、醫院、機關，TWD97） | 新北市資料開放平臺，2026-09-12 |
| `ntpc_parking.json` | 新北市路外公共停車場 1,415 列（TWD97、車位、時段、費率） | 新北市資料開放平臺，2026-09-12 |
| `compute_parcel_geometry.py` | 算宗地面積、外接矩形、矩形度、臨路候選 | 輸入 twland_raw.json、osm_roads_bbox.json |
| `parcels_shulin.geojson`、`parcels_geometry.csv` | 上一項的輸出（含每條邊的最近道路） | |
| `build_table4_draft.py` | 產表4 項目 7–25 草稿與各設施子欄位最近設施表 | 輸入上面所有資料 |
| `table4_draft.csv`、`table4_draft.md`、`facilities_nearest.csv` | 上一項的輸出 | |

## 重跑

```bash
cd 補查資料
python3 compute_parcel_geometry.py       # → parcels_shulin.geojson, parcels_geometry.csv
python3 build_table4_draft.py            # → table4_draft.*, facilities_nearest.csv（需 venv）
```

## 重抓資料（資料有更新或要換區段時）

```bash
# 地號 → 地籍多邊形（可一次多筆；回傳含蘆洲區同名段，看 properties.鄉鎮）
curl -sS -G "https://twland.ronny.tw/index/search" \
  --data-urlencode "lands[]=新北市,樹德段,1415" --data-urlencode "lands[]=新北市,樹德段,284" \
  --data-urlencode "lands[]=新北市,太平段,367" --data-urlencode "lands[]=新北市,太平段,917" \
  --data-urlencode "lands[]=新北市,文林段,317" -o twland_raw.json

# 新北市開放資料：分頁 JSON（每頁 size 筆，抓到不足一頁為止），或 /csv/file 整檔
curl -sS "https://data.ntpc.gov.tw/api/datasets/6dcff24a-838c-40fb-a9df-f1160afafe84/json?page=0&size=5000" -o ntpc_landmarks.json   # 重要地標
curl -sS "https://data.ntpc.gov.tw/api/datasets/b1464ef0-9c7c-4a6f-abf7-6bdf32847e68/json?page=0&size=1000" -o parking_p0.json      # 路外停車場（第 1 頁；第 2 頁 page=1）
curl -sS "https://data.ntpc.gov.tw/api/datasets/34b402a8-53d9-483d-9406-24a682c2d6dc/json?page=0&size=1000" -o bus_p0.json          # 公車站位（約 70 頁）
curl -sS "https://data.ntpc.gov.tw/api/datasets/5fe3a136-29cc-4695-a17e-6636a32c3342/csv/file" -o ntpc_parks.csv                     # 公園（整檔）

# OSM Overpass（POST；bbox 順序 南,西,北,東）
curl -sS -X POST "https://overpass-api.de/api/interpreter" --data-urlencode \
 'data=[out:json][timeout:120];way["highway"](24.978,121.409,25.003,121.430);out geom;' -o osm_roads_bbox.json
curl -sS -X POST "https://overpass-api.de/api/interpreter" --data-urlencode \
 'data=[out:json][timeout:180];(nwr["amenity"~"^(school|university|college|marketplace|bus_station|post_office|bank|hospital|clinic|townhall|crematorium|parking|grave_yard)$"](24.96,121.39,25.02,121.45);nwr["shop"~"^(supermarket|mall|department_store)$"](24.96,121.39,25.02,121.45);nwr["leisure"~"^(park|playground|garden)$"](24.96,121.39,25.02,121.45);nwr["place"="square"](24.96,121.39,25.02,121.45);nwr["landuse"="cemetery"](24.96,121.39,25.02,121.45);nwr["power"~"^(substation|tower|plant)$"](24.96,121.39,25.02,121.45);nwr["man_made"~"^(storage_tank|wastewater_plant|works)$"](24.96,121.39,25.02,121.45);nwr["railway"="station"](24.96,121.39,25.02,121.45);nwr["name"~"焚化|掩埋|污水|公墓|納骨|生命紀念|殯儀|變電所|市場|夜市|商圈"](24.96,121.39,25.02,121.45););out center;' -o osm_pois.json
curl -sS -X POST "https://overpass-api.de/api/interpreter" --data-urlencode \
 'data=[out:json][timeout:100];nwr["highway"="motorway_junction"](24.93,121.36,25.05,121.48);out center;' -o osm_junctions.json
```

Python 的 `urllib` 對 data.ntpc.gov.tw 會出 SSL 驗證錯誤，用 curl 抓。

## 注意

- 所有距離目前是直線、起點是評價單元質心。表3 正式要用區段中心點（4 個區段 polygon 還沒畫），通達型細項正式要用路線距離。
- 座標統一 EPSG:3826；WGS84 → 3826 用 `Transformer.from_crs("EPSG:4326","EPSG:3826",always_xy=True)`。
- 級距判定在程式裡只是暫定，正式判級交給計算引擎；程式輸出的「待」「※」都要人工處理。
