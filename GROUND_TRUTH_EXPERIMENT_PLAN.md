# Ground Truth Evaluation Readiness Analysis

日期：2026-09-17。研究：Independent Revisit + Ground Truth Localization Evaluation。

本次只分析並新增本文件；沒有修改程式、建立 evaluator、執行定位、重建/訓練 LingBot-MAP、新增 LightGlue 或操作 ESP32。下列資料夾、CSV、設定檔均為**未來配置建議，尚未建立**。

固定 mapping：`outputs/scenes/scene_20260818/mapping/`。新的 revisit images 絕不可放入 mapping inputs，也不可呼叫 split/mapping pipeline 重新建立此地圖。

## Readiness 結論

**可以準備與採集獨立重訪資料，但尚未具備直接產出可信 GT 評估的完整條件。**

| 項目 | 現況 |
|---|---|
| 固定 map 與 ORB raw pose | READY：有 NPZ、reference images、43-query baseline |
| Position/yaw 程式定義 | READY：可從實作確定，見第1節 |
| Map 與物理水平面的關係、metric scale | NEEDS VERIFICATION：-Y-up 只是使用約定，非重力/公尺驗證 |
| GT 原點、量測工具、control points、對齊 | NOT AVAILABLE：需要現場量測與獨立對齊 |
| Query 相機校正 | NOT READY：目前 K 來自 reference prediction、distortion=None，設定為 UNSET |
| 新手機是否與原 mapping 相同手機/鏡頭/拍攝模式 | UNKNOWN：不能由現有 NPZ 確認 |
| 54筆 GT 與 success thresholds | 尚未採集；thresholds 必須實驗前預先設定 |
| Evaluation script / alignment 工具 | 本輪不建立；現有程式不會自動完成此評估 |

可以先評估「未校正的現有 baseline」，但必須如實標示相機模型限制；不能因拍了 calibration board，就宣稱目前 localizer 已採用 calibrated query K。

# 1. 現有座標定義

## 1.1 原始碼與資料證據

- [orb_keyframe_localizer.py](Integrated_version/experiments/orb_keyframe_localizer.py)：`pose_from_pnp`、`result_to_pose`、`read_image`、`OrbKeyframeLocalizer.localize`。
- [run_lingbot_mapping.py](Integrated_version/experiments/run_lingbot_mapping.py)：`run`、`write_prediction_archive`。
- [demo.py](lingbot-map-main/demo.py)：`postprocess` 將解碼的 w2c 反矩陣轉為 c2w；`_get_world_points` 使用點預測或 depth 反投影。
- [localize_query_in_3d_viewer.py](Integrated_version/experiments/localize_query_in_3d_viewer.py)：`camera.up.set(0,-1,0)`，query forward=`(sin(yaw),0,cos(yaw))`。
- [build_rebuilt_navigation_map.py](Integrated_version/map/build_rebuilt_navigation_map.py)：`axis_indices`、高度與 X/Z grid 投影。
- [grid_navigation.py](Integrated_version/planner/grid_navigation.py)：`world_to_pixel`、`pixel_to_world`。
- [demo_server.py](Integrated_version/web/demo_server.py)：pose offset、snap-to-free、另一種模擬 yaw 計算。

本次唯讀檢查固定 NPZ：`extrinsic_c2w=(43,3,4)`、`intrinsic=(43,3,3)`，皆 float32；key 包含 world_points/depth/depth_conf，沒有外部 GT 或 metric alignment。第一張 mapping 的 R_cw 接近 identity，camera center 約 `(-0.001265,0.001402,-0.002045)`；這只支持「此張接近模型原點」，不能說它等於現場牆角或真實地面原點。

## 1.2 Position 與 PnP

以 W 表示 raw LingBot reconstruction frame，C 表示 query camera frame：

```text
PnP 回傳：P_C = R_wc P_W + t_wc

R_cw = R_wc^T
C_W  = -R_wc^T t_wc
P_W  = R_cw P_C + C_W

position_xyz = C_W = [X, Y, Z]
camera forward in W = f_W = R_cw [0, 0, 1]^T
```

`position_xyz` 是**相機投影中心**，不是手機中心、腳架中心、車輛中心或鏡頭朝向點；不是 PnP 的 tvec。GT 應量測使用中鏡頭的中心位置及其地面投影，手機外殼/支架偏移必須計入量測不確定度。

OpenCV camera frame 為影像右方 +X_c、影像下方 +Y_c、鏡頭前方 +Z_c；PnP 回傳世界到相機的變換。這是呼叫 API 的定義，不代表世界 frame 是 ENU/NED/ROS。[OpenCV PnP 官方說明](https://docs.opencv.org/4.13.0/d5/d1f/calib3d_solvePnP.html)

Raw map XYZ 與現場東西南北、牆壁、重力的對應：**UNKNOWN**。目前選 X/Z 為水平平面、-Y 為上，只是導航/展示的約定；是否近似真實地面必須另外確認。

## 1.3 Yaw：不可直接當現場方位角

程式：`yaw_deg = degrees(atan2(f_W.x, f_W.z)) % 360`。

| ORB yaw | 模型水平 forward |
|---:|---|
| 0° | +Z |
| 90° | +X |
| 180° | -Z |
| 270° | -X |

正方向是 **+Z 轉向 +X**。以右手 XYZ 代數描述，它相當於繞 **+Y** 的正向旋轉，而不是繞目前所稱上方 -Y 的右手正向。它是 forward 在 X/Z 的投影 heading，不是完整姿態的 Euler yaw，也沒有保存 query pitch/roll。

在「+X 向右、+Z 向紙面上方」的下圖中，yaw 增加是順時針；不要用任意 viewer 螢幕朝向推定順/逆時針。若 forward 幾乎平行 Y 軸，水平投影接近零，heading 不可靠；目前 raw JSON 只存 position/yaw，沒有完整 query R 或 forward norm，無法事後可靠檢查這個退化情況。第一輪要固定鏡頭近水平，仍須揭露這個程式限制。

```text
              +Z = navigation planar +y
               ^  ORB yaw 0
               |
  yaw 270  <--- O ---> +X = navigation planar +x
               |       ORB yaw 90
               v
              -Z  yaw 180

紙面朝外的法向：X cross Z = -Y（目前 viewer 的 up）
ORB yaw 增加：+Z -> +X -> -Z -> -X

raw map point/pose [X,Y,Z]
       | select X,Z（不是校正）
       v
planar p_L=[X,Z] -------- s R(theta), t --------> measured p_GT=[GT_X,GT_Y]
       |
       +--> navigation: x_m=X, y_m=Z（欄位叫m，不代表尺度已量測）
       +--> viewer:保留XYZ；camera.up=(0,-1,0)，不會把資料旋轉成GT
```

`result_to_pose` 直接傳原 yaw，但 Web simulator 使用 `atan2(delta_y,delta_x)`，兩者零方向與正方向不同；不能用模擬 pose 當 query GT evaluation 輸入。只讀 raw `*_result.json` 的 best.position_xyz / best.yaw_deg。

導航 grid 像素：`px=floor((X-origin_u)/resolution)`，`py=floor((origin_v-Z)/resolution)`；因此影像 row 向下時 Z 減少。這是 raster 排列，不是另一個物理座標翻轉。

禁止使用 Demo 預設 x offset=-1.53、snap-to-free 後的 pose、current_pose.json（rejected 時可能被填成0,0,0），或 floor-calibrated PLY 的點去混配 raw NPZ。

# 2. Ground Truth 與 LingBot Map 對齊

## 2.1 現場 GT 定義（新實驗規約，不是現有 repo 保證）

選固定且可重找的牆角**地面投影**為 GT origin；沿指定牆方向為 +GT_X；同一水平面內垂直方向為 +GT_Y。畫箭頭、拍全景與近照，明確選擇使 `GT_X cross GT_Y` 指向真實上方，避免默默引入鏡射。墙面不一定垂直/相互正交，應用直角工具或距離幾何檢查，不只憑目測。

GT yaw 定義為 `atan2(forward_GT_Y,forward_GT_X)`，範圍 [0,360)：0°=+GT_X，90°=+GT_Y；由上方向地面看，從 +GT_X 到 +GT_Y 為逆時針。這是實驗自行明定的平面角度，與磁北無關。

## 2.2 比較三種 transformation

令 p_L=[X,Z]^T，p_GT=[GT_X,GT_Y]^T：

| 模型 | 方程式 | 未知量 / 理論最少配對 | 適用條件 |
|---|---|---|---|
| Translation only | p_GT=p_L+t | 2；1個點 | 軸向與尺度已事先確認相同；目前不成立 |
| 2D rigid | p_GT=R(theta)p_L+t | 3；2個不同位置的點 | 單位尺度已確認為1；目前未驗證 |
| 2D similarity | p_GT=s R(theta)p_L+t，s>0 | 4；2個不同位置的點 | 允許統一尺度、平面旋轉與平移；目前最合理的起點 |

R(theta)=[[cos(theta),-sin(theta)],[sin(theta),cos(theta)]]；s 的單位是「公尺/模型單位」。推薦**無鏡射、單一全域的 2D similarity**，不是 affine、非均勻 XY scale 或依 test query 逐張校正。

兩點雖可在非退化情況決定 similarity，沒有多餘觀測檢查錯誤，**不建議只用兩點**。建議現場量6個固定 landmarks：4個事前指定 fit controls，2個事前指定 alignment check points；fit點分散且不共線，檢查點也分散。若資源有限，至少4個非共線點，但應清楚區分擬合殘差與獨立檢查，不能把 training residual 當對齊精度。

實驗前用 fit/check control geometry 確認對齊可用，再凍結 s、theta、t。Fit/check 殘差容許範圍：**NEEDS PREDEFINITION**，依量測工具與目標誤差設定，不在看 query 結果後放寬。只在 controls 上選方法；不能比較數種對齊後挑 test error 最小的。

## 2.3 Control points 要怎麼取得

1. 出發前在**固定 mapping 的 preprocessed images** 找穩定自然特徵，例如固定門框下角、柱腳、牆角、可辨識地磚交點。選能在實體現場指到相同物理點、不是反射面或可移動家具的位置。
2. 記錄 reference frame index、preprocessed pixel (u,v)，由同一份 raw `world_points[index,v,u]` 取得 map XYZ。保存完整 XYZ 和選點證據，不能從高度校正或展示縮放後的圖上讀模型座標。
3. Depth 邊緣/遮擋處可能對應錯面；對同一點以不同 mapping views 檢查一致性。單點、固定小區域或多視角合併的規則先訂好，不能事後選最有利的3D值。Control map selection uncertainty 也須紀錄，不能只算尺的誤差。
4. 現場量每個 landmark 的 GT_X、GT_Y，必要時用垂線投影到地面；最好一併量高度 GT_Z，用以檢查模型地面/垂直方向。保留照片和原始量測表。
5. Control points **不是54張 test query 的 camera positions**，不使用 test query 的 PnP pose、GT yaw 或預測誤差估 alignment。可以位於同一區域，但必須是獨立物理特徵和獨立量測。
6. 現場新貼的標記若沒有出現在固定 map，不能直接充當 map對應control。可作量測輔助，但不能假裝已有其map XYZ。若找不到足夠對應特徵，狀態為 ALIGNMENT NOT READY，不用test poses補救。

目前 repo 有 world_points 可供讀取，但沒有已驗證的 control-point picker / alignment evaluator；本文件不宣稱這些工具已存在。此次先準備可追溯的對應表，不要求重建地圖。

建議未来 `control_points.csv` 最小欄位：`control_id,role,reference_frame,u_px,v_px,map_x,map_y,map_z,gt_x_m,gt_y_m,gt_z_m,measurement_uncertainty_m,notes`；role只能 fit/check。以 session.json 指定共同NPZ版本、選點方法及map選點不確定度的估計方式。

## 2.4 平面假設是正式評估前的 Gate

2D similarity **不能校正模型的 roll/pitch 傾斜、非均勻伸縮或局部重建變形**。控制點平面殘差小，也不單獨證明相機高度所在平面同樣正確；map傾斜時，地面landmarks與高處相機可能有不同水平偏移。

用分散的地面點、垂直固定結構及其量測高度，檢查 raw map 的-Y是否近似真實鉛直、XZ是否近似地面。檢查尺度/殘差是否隨位置或高度有系統變化，不用viewer看起來正就算通過。

若不成立：暫停「平面公尺position/yaw準確度」的正式宣稱，標記 NEEDS VERIFICATION。未來可能需要以獨立3D controls作固定3D similarity/leveling；此時僅有raw yaw不足以正確轉換傾斜後heading，需完整query rotation/forward證據。這是後續需求，不在本輪修改程式或重建map。

## 2.5 Position 與 Yaw 必須用同一個對齊

平面假設成立時：

```text
estimated_GT_position = s * R(theta) * [X,Z] + t

psi = radians(raw_ORB_yaw)
forward_L = [sin(psi), cos(psi)]
forward_GT = R(theta) * forward_L
estimated_GT_yaw = atan2(forward_GT[1],forward_GT[0]) in degrees, modulo 360

等價：estimated_GT_yaw = (theta_deg + 90 - raw_ORB_yaw) modulo 360
```

Translation 不影響方向；positive uniform scale不影響角度。不能直接加theta到raw yaw，也不能用測試yaw另外擬合一個offset。若必須鏡射才能對齊，先查GT軸向、pixel方向及對應點，不能讓fit默默選reflection；以上yaw簡式只適用於det(R)=+1。

# 3. Ground Truth CSV Schema

每列一張預先排定的 query；UTF-8、逗號分隔、十進位點。不是每個position只一列，也不是每個影片frame都自動成為獨立sample。

```csv
query_image,session,round,point_id,direction_id,gt_x_m,gt_y_m,camera_height_m,gt_yaw_deg,position_uncertainty_m,yaw_uncertainty_deg,notes
```

| 欄位 | 規則 |
|---|---|
| query_image | 相對於session目錄的影像路徑，例如 images/P01_D01_R01.jpg；不存機器absolute path |
| session | 例如 revisit_202609xx_a；日期待實際採集填寫 |
| round | 1/2/3，代表不同重新放置回合，不是連拍編號 |
| point_id | P01..P06，地面位置標記 |
| direction_id | D01..D03；只作設計組別，實際yaw看gt_yaw_deg |
| gt_x_m / gt_y_m | 該次使用鏡頭投影中心的地面位置；每次放置確認，不直接抄腳架中心 |
| camera_height_m | 該次鏡頭中心相對GT地面的高度；固定目標高度但記錄實際值 |
| gt_yaw_deg | 第2節GT角度，範圍[0,360)，記錄實際量測方向而非手機磁羅盤數值 |
| position_uncertainty_m | 水平鏡頭位置的保守誤差半徑估計，含量尺、垂線、安裝偏移與重放；非演算法誤差 |
| yaw_uncertainty_deg | 朝向量測的保守誤差半寬，含角度工具及鏡頭/支架對齊；非inlier reprojection error |
| notes | 遮擋、設備問題、重新拍攝原因；正常可留空 |

不填猜測數字。缺少GT、不確定度或必要影像時標為資料不完整，正式評估前補查；不能填0代替未知值。Uncertainty採「保守界限估計」而不是未經實驗支持的1-sigma/95% confidence，估計依據寫在session.json。

驗證唯一性：query_image唯一，(session,round,point_id,direction_id)唯一；預期6×3×3=54組；每列影像存在；數值有限；不確定度非負；樣本不能同名不同副檔名，因現有runner按stem命名結果。

不必每列重複手機型号、map版本或alignment。以小型 `session.json` 保存共同資訊：schema_version、GT軸向示意/照片路徑、camera裝置/鏡頭/app模式/解析度/方向、目標高度、calibration狀態與檔案、抽樣/重拍規則、量测工具與uncertainty定義、固定map路徑與hash、預先設定thresholds及protocol版本。若用影片取幀，另需 source_video 和 source_frame_index 的對照；第一輪建議直接54張照片以減少此項複雜度。

# 4. 最小資料夾配置

目前已有 `data/scenes/scene_20260818/` 和 `outputs/scenes/scene_20260818/`，因此沿用scene分組，不另開平行的全域data/revisit架構。

```text
data/scenes/scene_20260818/
  revisit/revisit_202609xx_a/             # 新資料，永久研究原始證據
    images/                             # 只放54張正式query
    ground_truth.csv
    control_points.csv
    session.json
    evidence/                           # 量測原稿、場地/GT軸照片、保留重拍證據
    calibration/                        # 同模式的校正影像、未來K/distortion結果

outputs/scenes/scene_20260818/
  mapping/                              # 原有固定包，不改、不加入query
  results/orb/                          # 原有in-sequence證據，不覆蓋
  revisit/revisit_202609xx_a/
    alignment.json                      # 未來一次凍結的s,R,t、fit/check IDs、殘差
    runs/orb_baseline_001/
      localization/                     # 未來per-query raw JSON及runner summary
      current_pose.json                 # 隔離runner的pose寫入，不作evaluation輸入
      run.json                          # 實際CLI/版本/K模式/gate/hash/timer範圍
      per_query_metrics.csv             # 未來evaluator輸出
      evaluation_summary.json
```

不複製大NPZ、不變動既有symlinks。Mapping freeze清單應涵蓋predictions.npz、43張preprocessed images、prediction/run metadata；PLY亦可hash以識別展示版本。記錄hash不是建立新的模型。對照ground_truth和images另保存hash，評估後再次核對。

這份benchmark不是可任意刪除的Demo暫存，原始影像/GT/controls應備份保留；重跑產物用新run_id，不覆蓋舊結果。`data/`、`outputs/`目前被Git忽略，不能以為commit本文件就備份了資料。

**Runner寫入風險：**`analyze_external_queries.py` 未指定output-dir會写回原scene external_query_results；未指定pose-file會寫原scene current_pose.json。未來必須明確指定 mapping-dir、query-dir、output-dir、pose-file；不能使用整合pipeline、Web Demo或同一live session當正式評估入口。本輪不提供或執行會寫檔的命令。

# 5. 第一輪現場實驗：6 × 3 × 3

## 出發前設計

1. 挑6個可量測、位於既有map涵蓋範圍的室內位置，涵蓋不同區域/距牆位置，避免都擠在單一角落。選點依据場地與mapping畫面，不看revisit定位成績。
2. 每個位置預定3個viewing directions，朝不同已建圖結構。方向不必所有點都同樣角度，也不強迫看向地圖外；在第一張正式query前寫定18個目標方向及其GT角度。不得看匹配數再換方向。
3. 固定一支手機、一顆後鏡頭、同一app/模式、方向及輸出解析度；關閉digital zoom、自動鏡頭切換與會改變裁切的可控選項。優先固定焦距/對焦，記錄無法關閉的自動處理。原mapping是否同一手機為UNKNOWN，不作假設。
4. 固定鏡頭中心目標高度H，鏡頭近水平、roll固定；H由實際支架與場地決定，出發前寫入protocol，不由repo猜一個值。
5. 第一輪保持接近mapping的光線、家具與門的位置；用照片/筆記記錄差異，不改場景來迎合結果。一次獨立重訪54張，只代表一個場景/一次session，三round不是三種獨立環境。
6. 準備手機夾/腳架、捲尺或量距工具、垂線、直角工具、水平儀、量角器/角度盤、標記膠帶、量測表及備份。先確認固定手機時能以使用中鏡頭而非外殼中心對準。

## 現場操作

- 先建立GT origin與兩條軸，確認直角；量controls及獨立check points，拍可追溯照片。新標記盡量放鏡頭視野外，避免大幅改變被定位的場景特徵。
- 標6個鏡頭垂足位置，量各點X/Y；以垂線確認鏡頭投影，量實際高度。旋轉手機時若不是繞鏡頭中心，必須重新校正位置，不能假設三方向的相機位置完全相同。
- 用水平地面上的方向線、量角器及相機光軸的機械對齊標記建立heading；不用室內磁羅盤當GT。可以用已量測的遠處目標輔助對準，但需計入支架/光軸偏差，不能用ORB結果幫忙對準。
- 按事先固定或事先隨機化的18組順序完成round1；移開並重新安裝/放置後做round2、round3。每個round中的每個point/direction均重新放置、確認位置/朝向，不原地按三次快門。
- 每次拍攝前/當下填實際鏡頭X/Y、高度、yaw及量測不確定度。名義座標可共享，但實際偏差須確認；不可只填「P01所以座標一樣」。
- 每次穩定後按預定規則拍一張。若用固定時長短片，預先固定取中間frame，不能後看清晰度/定位再挑最佳frame；第一輪直接拍照較簡單。
- 允許的重拍僅限事前列出的採集失敗，例如檔案未保存、錯鏡頭或拍攝前明顯支架移位。保留原檔與原因，採固定替代規則；不要按定位成功、inlier數或看完所有照片再選最好的一張。一般困難影像應作為測試樣本保留。
- 拍完現場核對54組、檔案與量測對照；整個過程不執行localization或查看confidence。

**每次需量的物理量：**使用中鏡頭的地面投影X/Y、鏡頭中心高度、光軸水平heading，以及工具/重放帶來的位置與角度不確定度。Pitch/roll以水平儀和固定支架約束；若未能固定，需記錄偏離並重新評估2D yaw有效性，不能聲稱量測了完整6DoF。

# 6. 未來評估指標與判斷規則

## 6.1 每張 Error

對raw best pose套用**同一個已凍結alignment**：

```text
position_error_m = sqrt((pred_GT_X-gt_x_m)^2 + (pred_GT_Y-gt_y_m)^2)

signed_yaw_error_deg = ((pred_GT_yaw-gt_yaw_deg+180) modulo 360) - 180
yaw_error_deg = abs(signed_yaw_error_deg)
```

359°和1°的誤差為2°；180°邊界的絕對誤差為180°。此處position是2D水平位置error，camera_height用於量測一致性，不可因此報3D XYZ accuracy。

單張欄位至少包含query id、raw status、confidence、accepted、是否有finite candidate pose、對齊後pose、position/yaw error、GT success判定、latency、GT完整性/失敗原因。拒絕或缺pose不可用(0,0)補值，不可用GT補預測。

## 6.2 Gate 與 GT Success 是兩件事

- `A`（accepted）：與現有baseline一致，raw status=localized、有效best pose且confidence≥0.35。記錄全部參數；正式前可核定protocol，但不得看到54張成績後改gate。
- `G`（candidate geometrically correct）：存在有限candidate pose，且position_error≤T_pos、yaw_error≤T_yaw。
- **T_pos與T_yaw：需要實驗前預先設定。** 依研究應用需求與人工量測/對齊的不確定度決定；目前repo沒有可採信的現成threshold。本文件不任意訂數字。若尚未設定，只報連續error分布與acceptance，不報GT success或false acceptance/rejection。
- 最終GT localization success：`A AND G`。有正確candidate但系統拒絕，不是成功交付定位。
- 若對齊殘差或人工不確定度與threshold同量級，標示borderline/measurement-limited；不能忽略量測誤差或在看完結果後放寬threshold。邊界判定/敏感度報告方式亦須事前設定。

| Gate | Candidate GT error | 判定 |
|---|---|---|
| A=true | G=true | True acceptance / 已交付的GT success |
| A=true | G=false | False acceptance：系統放行錯誤pose |
| A=false | G=true | Observable false rejection：原始候選正確卻被拒絕 |
| A=false | G=false且有候選 | True rejection of incorrect candidate |
| A=false | 沒有有效候選 | No-pose rejection；G不可判，不能自動算true/false rejection |

**目前false rejection能力有限：**當PnP無解時沒有可量誤差的候選；GT位置存在不代表演算法曾找到正確候選，更不代表該影像理論上一定可定位。這類樣本是operational failure，但false-rejection correctness為UNKNOWN；不能把54-accepted直接叫false rejections，也不能把無pose當GT-confirmed true rejection。

## 6.3 彙總與分母

| 指標 | 定義 |
|---|---|
| Acceptance rate | N_accepted / N_attempted；計畫N=54，包含無pose/失敗 |
| Rejection rate | N_rejected / N_attempted；完整評估且二分時=1-acceptance |
| Position mean / median / P90 | 主表對accepted且GT完整的samples統計，**包括false accepts**；必報n |
| Yaw median / P90 | 同上，對wrapped absolute yaw error統計，必報n |
| 所有有限candidate error | 可加附表，包括rejected candidates，標示與主表不同分母 |
| GT localization success rate | N_(A AND G) / N_attempted；no-pose計失敗，缺GT另列資料缺陷 |
| False acceptance count | N_(A AND NOT G)，僅GT可判定 |
| False acceptance fraction among accepted | N_(A AND NOT G) / N_accepted；分母需有GT，否則標示缺失 |
| False acceptance burden | N_(A AND NOT G) / N_attempted，名稱與上列分開 |
| Observable false rejection count | N_(NOT A AND G)，只限有有效candidate與GT |
| Observable FR fraction | 上列 / N_rejected_with_valid_candidate_and_GT；不外推到無pose樣本 |
| 可選classifier FPR/FNR | 只在G可判子集：FPR=FP/(FP+TN)，FNR=FN/(FN+TP)，同時報excluded no-pose |
| Latency | 所有有latency紀錄的attempts之count/mean/median/P90/min/max，另報缺失/exception數 |

P90預先固定linear interpolation，無樣本分母為0時回報N/A，不能回報0 error。只對成功且error小的樣本報median會選擇性低估誤差；主表不能排除false accepts。若accepted少，低median不代表系統好，必須搭配coverage/GT success。

Latencies沿用localize()內部timer：包含query讀取/resize/ORB/matching/reference search/PnP，排除map/reference初始化、capture、結果寫入與viewer。未來如量端到端需另名紀錄，不與211.679ms直接混比；固定環境與run流程，不挑最快一輪。Exception/timeout沒有latency時不可補0，也不可悄悄刪除attempt。

保留point×direction×round分組結果；54張不是54個獨立場景，不用相鄰連拍或多次重跑擴大樣本數。資料不完整應先修復或揭露，不在結果出來後偷偷改分母。

# 7. Camera Calibration / Preprocessing Readiness

現況：query經cv2.imread直接resize到518×294；mapping前處理用PIL、EXIF orientation、patch-size對齊及必要center crop。PnP使用各reference預測K且distortion=None。`visual_navigation/config/camera.json`為UNSET；第一個reference K約fx=480.747、fy=480.392、cx=259、cy=147，**這不是新手機的校正值**。

## A. 第一輪一定要做

1. **固定並記錄image formation。** 同一手機/鏡頭/輸出方式，固定解析度、方向、焦距、無digital zoom，盡可能固定focus與裁切。不要混用相簿照片與IP Webcam截圖而假設其K相同；第一次確定一條路徑後54張全部使用同一路徑。
2. **確認最終decoded image geometry。** 不只看EXIF的width/height，確認旋轉、鏡像、實際長寬比；使用非鏡像後鏡頭。保存原檔，任何前處理規則事前固定且可追溯，不逐張人工調整來提高matching。
3. **採集同模式校正資料並在正式評估前檢查K/畸變。** 可用量過格長、平整的棋盤板，在不同位置、距離、傾角覆蓋中心與邊緣；保留原圖、格長與量測工具資料、校正殘差/獨立檢查影像。校正不是使用test query GT調參。本輪只規劃，不執行/建立calibration script。Board資料放calibration/，絕不混進正式query。
4. **校正用途必須如實區分。** 取得K/distortion後可診斷目前reference-K假設的偏差；現有ORB不會讀取這份K。第一輪若保持程式不變，就命名為「frozen ORB baseline / reference-predicted K / no explicit distortion compensation」，仍可量測此系統的GT errors，但不能稱已校正query定位。
5. **不要偷偷undistort後沿用不相容K。** 去畸變會有新的effective K和可能crop；目前不同reference K還可能不同。只校正圖片不改PnP內參處理，不能保證修正幾何。正式使用calibrated-query K需要後續獨立授權的介面/前處理工作，與這次「不修改ORB」分開。若研究要求校正版benchmark，須等該缺口完成再跑正式測試。
6. **對焦/支架與GT相機中心一致。** 固定手機安裝方式與鏡頭位置，控制roll/pitch；無法精確定位光學中心時把機械偏移納入uncertainty，不用手機中心冒充。

影像縮放須對應縮放K，crop須調整principal point；在新pixel座標下使用舊K不是由「同一支手機」就能合理化。OpenCV官方說明K與pixel尺度的關係；此處是未來幾何一致性要求，不表示目前程式已實作。[OpenCV calibration 官方說明](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html)

## B. 可以之後改善

- 明確支援query自己的calibrated K、distortion與統一resize/crop/EXIF變換，另立run版本，不能覆蓋第一輪baseline結果。
- 保存query完整rotation/forward及其水平投影長度，支持傾斜地圖的heading轉換與退化檢查。
- 更精確的光軸/支架外參、不確定度傳播、rolling-shutter/穩定器影响分析與多手機、多光照獨立session。
- 更高精度外部量測。這不是本輪必要的設備升級，也不涉及ESP32、LightGlue或模型重訓。

# 8. 五階段現場 Checklist

## BEFORE LEAVING FOR THE TEST SITE

- [ ] 固定scene_20260818 mapping；規劃hash清單與備份，不呼叫mapping pipeline。
- [ ] 在mapping原始preprocessed畫面選6個可回現場量的自然landmarks，預指定4 fit / 2 check，保存frame/pixel對應。
- [ ] 畫GT origin、+X、+Y及yaw方向示意；確認「GT零度沿+X，ORB零度沿+Z」。
- [ ] 訂好6個位置×3方向×3round、檔名與拍攝/重拍規則，不看定位後換點。
- [ ] 決定鏡頭高度、裝置/鏡頭/app/解析度/方向/焦距；確認原mapping相機未知的限制。
- [ ] 決定本輪為不改程式的reference-K baseline；若要求calibrated-query版，記錄執行阻擋項。
- [ ] 準備校正板、手機固定架、垂線、量尺、直角/角度工具、水平儀、量測表、電源與備份。
- [ ] 預先設定T_pos、T_yaw、alignment fit/check容許條件、uncertainty及資料缺失規則；若未定，不允許事後憑成績訂threshold。

## AT THE TEST SITE

- [ ] 記錄日期/session與環境，光線盡量接近mapping；不執行定位看成績。
- [ ] 建GT座標並檢查直角，拍原點/軸向證據；量controls及check points的XYZ/不確定度。
- [ ] 若controls無法對應現有map，標記alignment不足，不改用test camera positions。
- [ ] 完成同拍攝模式calibration images；與54張query分開存放。
- [ ] 每次拍攝量使用中鏡頭垂足X/Y、中心高度、光軸yaw，確認roll/pitch與無zoom/鏡頭切換。
- [ ] 三round都移開重新放置；切換方向也檢查鏡頭中心位移，不原地連拍冒充重複量測。
- [ ] 逐張記錄uncertainty與query id，保存重拍原因與原始檔，不挑定位成功照片。
- [ ] 離場前核對54組影像和量測，補的是遺漏/記錄問題，不是低matching分數。

## AFTER DATA COLLECTION

- [ ] 依第4節將原圖、GT、controls、calibration、量測照片分開存，至少另做一份備份。
- [ ] 檢查54組唯一性、image路徑/解碼/方向、數值單位及缺失，不默默填0。
- [ ] 不覆寫原圖；預处理版本有獨立路徑/規則，GT位置參考的鏡頭不變。
- [ ] 只用獨立fit controls估scale/rotation/translation，check points評估；不開test localization結果。
- [ ] 驗證XZ近似地面及高度差的影響，記錄alignment residuals與uncertainty；失敗則暫停正式metric claims。
- [ ] 凍結alignment、GT、影像選擇、thresholds和protocol版本，記錄hash。

## BEFORE RUNNING LOCALIZATION

- [ ] 確認mapping hash未變；54張revisit沒有參與mapping或alignment fitting。
- [ ] 僅使用獨立query-dir；新run的output-dir與pose-file都明確指定，不覆蓋原scene結果。
- [ ] 固定ORB參數；與原43-query入口比較時明確frame_stride=1，不能誤用class預設5。
- [ ] 明確記錄reference-predicted K / distortion=None，或有另行驗證的校正版本；不能混稱。
- [ ] 停用Demo offset/snap，評估只讀raw best pose，不讀published的失敗零位姿或模擬pose。
- [ ] Evaluator尚未建立時，不把手動看viewer當完成GT評估；本次分析不執行這一步。
- [ ] 確認未來evaluator處理90度/符號差、yaw wrap、缺pose、分母和no-pose FR=UNKNOWN。

## BEFORE REPORTING RESULTS

- [ ] 列N_attempted、accepted、rejected、exception、no-pose與GT缺失數；交代所有排除。
- [ ] 報accepted全集（含false accepts）的position mean/median/P90與yaw median/P90，附樣本數和coverage。
- [ ] 報T_pos/T_yaw、GT success rate與明確分母的FA/observable FR；threshold未預定則不報這些判定。
- [ ] 提供map/GT/alignment/run版本、control fit/check殘差、量測不確定度及相機模型限制。
- [ ] Latency標示計時區段，不能把localize timer叫端到端；不挑最快run。
- [ ] 明確寫一次獨立重訪session、54次重新放置樣本、同一室內map，不聲稱跨場景泛化。
- [ ] 不把2D position誤寫3D accuracy，不把meter欄位當scale驗證，也不宣稱實車自主導航。
- [ ] 再核對固定mapping與原始GT未更動，保留所有raw results與失敗案例。

## 本輪尚待確認的清單

現場GT原點/軸、目標高度、18個viewing directions、手機實際成像模式、工具精度、T_pos/T_yaw、control fit/check允許殘差、XZ平面假設與query calibration診斷：**全部需要現場/實驗前確認，repo無法代答。**

這一輪最重要的不是先收滿54張，而是確保「相機中心GT可量、heading定義一致、controls獨立、scale/平面假設可檢查、樣本選擇不受結果影響」。滿足這些條件後，才適合進入下一輪evaluation實作。
