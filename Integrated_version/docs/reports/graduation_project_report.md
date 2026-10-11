# 畢業專題報告整理稿

題目：單眼 3D 重建地圖之室內視覺重定位與導航影響評估

版本：根據 `report_benchmark_20260926T112228Z` 與本機既有 runtime 輸出整理

## 一、專題概述

本專題希望探討一個實際的室內機器人問題：在只有單眼 RGB 相機的條件下，系統能否先由影像建立場景的 3D 參考地圖，再利用後續影像估計相機在地圖中的位置與方向，最後把定位結果提供給路徑規劃與導航模擬使用。

整體流程可分成三個部分：建圖、重定位與導航。任何一個部分的誤差都可能影響後續結果。例如，單眼重建的尺度與幾何若不穩定，會影響定位；定位若低信心或延遲過高，會影響路徑追蹤；導航若直接使用錯誤姿態，則可能產生不安全的控制輸出。

本專題採用 LingBot-MAP 開源模型處理單眼影像並產生 3D 重建資料。本專題的研究重點不是重新訓練影像模型，而是把開源模型產生的重建結果接入一套可評估的定位與導航流程。專題端整合了 mapping/query 資料流程、ORB 視覺特徵定位、PnP/RANSAC 姿態估計、點雲增量融合、導航格網、dry-run 控制命令與網頁展示。

目前主要實驗將影像分成 mapping 與 query。mapping 影像用來建立固定參考地圖；query 影像則用來測試系統能否在該地圖中找出相機姿態。定位結果再作為導航模擬的輸入。這樣的設計讓系統可以先在固定資料與固定地圖上分析定位及融合流程，再逐步測試 RTSP 影像與前端介面。

| 模組 | 使用方法 | 目的 |
|---|---|---|
| 建立場景參考 | 使用 LingBot-MAP 處理單眼 RGB 影像，整理 3D 重建資料與彩色點雲 | 建立後續定位與導航使用的參考地圖 |
| 估計相機姿態 | 使用 ORB 特徵匹配，並以 PnP/RANSAC 估計相機位置與方向 | 取得 query 影像在參考地圖中的 pose |
| 評估地圖與導航 | 測試點雲增量融合、A* 路徑規劃、Pure Pursuit 與安全停止 | 評估定位結果如何影響導航流程 |

## 二、個人貢獻

在本專題中，我主要負責系統整合與測試，將建圖、相機定位、地圖更新、導航及前端顯示等功能串接成可執行的 prototype。我也確認各階段的資料格式、輸入輸出與座標設定，並使用離線資料、GPU 主機與 RTSP 即時影像逐步檢查系統運作情形。

在相機定位方面，我參與 ORB + PnP/RANSAC 基準流程的整合與驗證。系統會從 query 影像中擷取 ORB 特徵，與 reference map 中的 mapping frame 進行比對，再利用 2D-3D 對應估計相機的位置與方向。RANSAC 用來排除不一致的配對；confidence gate 則用來避免低信心姿態被送進導航流程。

在地圖更新方面，我參與 local point cloud replay、window-based LingBot-MAP backend、persistent worker 與 voxel fusion 的測試。這些測試分別用來檢查既有 `world_points` 的增量融合、模型載入成本、單個 window 推論成本、archive 輸出成本，以及 fast path 對 I/O 延遲的影響。

此外，我也參與 RTSP 影像輸入、latest-frame queue、即時地圖狀態輸出、網頁 API 與導航 dry-run 的整合測試。這些測試用來檢查影像輸入、地圖更新、定位狀態與安全停止之間的連動關係。

| 工作項目 | 個人貢獻 |
|---|---|
| 資料與重現流程 | 整理 mapping/query 資料、mapping package 檢查、實驗輸出規則與 benchmark artifact |
| 定位整合 | 整合 ORB、2D-3D correspondence、PnP/RANSAC、confidence gate 與 pose gate |
| 地圖更新 | 測試 local point backend、prediction replay、window replay、voxel fusion、persistent worker 與 fast path |
| 導航與驗證 | 參與 A*、Pure Pursuit、dry-run safety stop、RTSP 及前端資料流測試 |

## 三、目前成果與驗證

本專題目前已完成一套研究型 prototype，能把單眼重建地圖、視覺重定位、地圖增量融合、導航模擬與前端展示串接起來。以下列出最能代表成果的指標，重點放在「系統做到了什麼」以及「這個數字代表什麼」。

### 3.1 系統整合完成度

| 項目 | 目前成果 | 代表意義 |
|---|---:|---|
| 程式編譯 | PASS | 整合後的 `Integrated_version` 可正常編譯 |
| 單元測試 | 36 tests OK | 核心導航、安全停止、點雲融合與 runtime 模組通過測試 |
| 控制模式 | dry-run | 已能輸出導航命令紀錄，但尚未啟用 ESP32 實車控制 |
| 前端展示 | 可讀取 live map / pose / status | 可視化地圖狀態、點雲與定位資訊 |

這代表目前不是只有單一演算法測試，而是已經有一條可執行的整合流程。不過目前仍屬研究 prototype，實車閉環控制與長時間 RTSP 穩定性尚未完成驗證。

### 3.2 視覺重定位成果

| 測試項目 | 重要數據 | 說明 |
|---|---:|---|
| 固定 query set | 43 張 query 中 41 張通過 | Acceptance Rate = 95.35% |
| 固定 query set 延遲 | median latency = 214.171 ms | ORB + PnP/RANSAC 完成單張 query 定位的中位處理時間 |
| 固定 query set confidence | mean confidence = 0.9636 | 通過定位的結果具有較高信心分數 |
| 同場景影片 replay | 前 30 幀全部通過 | Acceptance Rate = 100% |
| 影片 replay confidence | mean confidence = 0.9864 | 同場景連續影像中定位結果穩定 |
| 影片 replay 延遲 | median latency = 334.434 ms | 前 30 幀 ORB localization 的中位延遲 |
| confidence threshold | 0.5 | confidence 大於或等於 0.5 才接受定位結果 |

這些結果顯示，在 `20260818` 同場景與固定 reference map 下，ORB + PnP/RANSAC 可以提供可用的視覺重定位結果。特別是固定 query set 的 41/43 與影片 replay 的 30/30，代表目前流程能穩定產生一批可被系統接受的 pose。

需要注意的是，這裡的 Acceptance Rate 是「通過 confidence gate 的比例」，不是實際定位準確率。因為目前沒有外部 ground truth，所以不能宣稱 position error 或 yaw error；這兩項在正式研究表格中應標示為 `NOT AVAILABLE`。

### 3.3 地圖增量融合成果

| 測試項目 | 重要數據 | 說明 |
|---|---:|---|
| prediction replay 更新次數 | 34 次 map update | 使用既有 `world_points` 測試增量融合流程 |
| 最終 voxel 數 | 33,947 voxels | 點雲經 voxel fusion 後的地圖規模 |
| 平均更新延遲 | 354.894 ms | 34 次更新的平均融合與輸出時間 |
| p50 / p95 延遲 | 356.565 ms / 379.322 ms | 更新延遲集中在約 0.35 秒等級 |
| peak RSS | 約 828.828 MB | 該批次測試中的主記憶體使用峰值 |

這組結果支持「點雲增量融合流程可運作」：系統可以依序處理局部點雲、合併重複 voxel，並輸出可供前端讀取的 live map。這對導航很重要，因為地圖不應只是一次性的靜態檔案，而需要能隨著資料輸入逐步更新。

不過，prediction replay 使用的是已經存在於 `predictions.npz` 的 `world_points`，所以這項結果不能被描述成每張新 RGB 影像都重新完成即時 3D inference。

### 3.4 LingBot-MAP worker 優化成果

| 測試項目 | 重要數據 | 說明 |
|---|---:|---|
| 模型載入時間 | 約 11.82 秒 | persistent worker 啟動時載入一次模型 |
| fast path 第二個 window | backend total = 1,099.387 ms | 後續 window 不需重複載入模型 |
| archive mode 第二個 window | backend total = 3,099.299 ms | 保留完整 archive 時 I/O 成本較高 |
| fast path archive write | 0.0 ms | fast path 不寫出每個 window 的完整 `predictions.npz` |
| 測試 window 數 | 2 windows | 可證明方向有效，但不足以代表長時間 FPS |

這項測試的意義在於：若每個 window 都重新啟動模型，系統會一直重複付出模型載入成本；改成 persistent worker 後，模型載入集中在一開始。再加上 fast path 直接取出 `world_points`，可以避免每個 window 寫入完整 archive 的額外 I/O。

目前只有兩個 window 的短測，因此適合用來說明「常駐模型與 fast path 有降低重複成本的效果」，但還不能用來宣稱長時間 real-time SLAM 效能。

### 3.5 即時輸入、前端與安全停止

| 項目 | 目前結果 | 說明 |
|---|---:|---|
| live mapping 補充測試 | 120 frames，4 次 map update | 背景建圖與 live map 狀態曾成功串接 |
| live fused points | 4,934 points | 前端可讀取增量融合後的點雲結果 |
| localization worker | 119 frames processed，0 dropped | ORB worker 可處理輸入影格 |
| 該輪定位狀態 | lost | 即時測試中未取得可用定位，不能宣稱 RTSP 定位完成 |
| safety stop | 已整合 | 低信心、定位遺失或 pose 過期時輸出停止命令 |

這部分說明系統已經具備即時資料流的雛形：影像輸入、背景建圖、live status、前端點雲與導航狀態可以串接。然而 RTSP 正式 benchmark 曾發生連線失敗，因此 RTSP 即時效能仍應標示為 `NOT VERIFIED`。目前也沒有啟用 ESP32 實車控制，所有控制命令都維持 dry-run。

### 3.6 目前可以主張與不能主張的範圍

| 可以主張 | 不能主張 |
|---|---|
| 已整合單眼重建地圖、ORB 重定位、點雲融合、導航模擬與前端展示 | 已完成真正 online monocular SLAM |
| 在 `20260818` 同場景資料上，定位流程有高 acceptance rate | Acceptance Rate 等於實際定位準確率 |
| Prediction replay 可完成 34 次增量地圖更新 | 每張新 RGB frame 都已即時重新推論 3D map |
| Persistent worker 與 fast path 能降低重複模型載入與 I/O 成本 | 兩個 window 足以代表長時間 FPS |
| 低信心或定位遺失時可觸發 dry-run safety stop | 實車馬達閉環控制已驗證完成 |

## 四、設計考量

本專題的設計重點不是把所有功能一次做到最複雜，而是先讓建圖、定位、導航與展示之間的資料流可檢查、可量測、可停止。以下是目前系統最重要的設計考量。

### 4.1 先固定地圖，再評估定位與導航

本專題先使用固定 mapping package 建立 reference map，再用 query 影像測試相機能否重新定位。這樣做的好處是可以把問題拆開：先確認 reference map 是否可用，再確認 ORB + PnP/RANSAC 是否能在該地圖中找到 pose，最後才把 pose 送入導航。

如果一開始就直接做 RTSP 即時建圖與導航，錯誤來源會混在一起，難以分辨是建圖失敗、定位失敗、座標錯誤、延遲過高，還是導航控制問題。

### 4.2 影像、點雲與姿態必須使用一致座標

`20260818` 場景採用 `-Y-up`，導航則投影到 X/Z 平面。這代表 3D viewer、ORB pose、voxel map 與導航格網都必須遵守同一套座標理解。

如果只把點雲旋轉到看起來正確，卻沒有同步轉換相機姿態與 3D points，前端會看起來有地圖，但相機位置、導航路徑與實際幾何會對不起來。因此本專題把座標一致性視為整合重點，而不是單純把點雲畫出來。

### 4.3 用 confidence gate 保護導航流程

定位結果不一定每次都可靠，因此系統不能只要有 pose 就拿去導航。本專題使用 localization confidence threshold 作為接受門檻；當 confidence 太低、pose 過期或 localization lost 時，NavigationManager 會輸出零速度或 safety stop。

這個設計讓定位模組和導航模組之間有明確的安全邊界。它不能保證實車安全，但能避免 prototype 在軟體層面把明顯不可信的位置直接交給控制流程。

### 4.4 使用 latest-frame queue 控制即時延遲

RTSP 或影片輸入可能比 ORB localization 或 LingBot-MAP inference 更快。如果每一幀都排隊等待處理，系統最後會處理到很久以前的影像，造成「看似有 FPS，但實際反應很慢」的問題。

因此系統採用 latest-frame queue，只保留最新影格，必要時丟棄舊影格。這樣可以控制反應延遲，但也必須記錄 dropped frames、processed frames 與 frame age，才能知道即時性是用多少資訊損失換來的。

### 4.5 將重建推論與點雲融合分開量測

Prediction replay、LingBot-MAP worker、voxel fusion 代表不同層級的工作。Prediction replay 測的是既有點雲資料如何融合；LingBot-MAP worker 測的是影像 window 如何重新推論點雲；voxel fusion 測的是如何控制地圖大小並持續輸出 live map。

把這些階段分開量測，可以避免用一個總延遲混淆不同瓶頸。例如 persistent worker 的模型載入是 session-level 成本，不能每個 window 重複相加；fast path 的 archive write 為 0 ms，也不能和保留完整 archive 的流程直接混稱為同一種輸出模式。

### 4.6 前端優先顯示研究狀態，而不是只追求畫面好看

前端目前的重點是讓研究流程可觀察，包括 map version、point count、mapping status、localization status、pose 與 safety stop。這些資訊比單純漂亮的 3D 視覺效果更重要，因為研究報告需要知道系統每一步是否真的更新、是否真的定位、是否因低信心而停止。

後續可以再加入可旋轉 Three.js 3D viewer 與車體模型，但在目前階段，前端主要任務是成為驗證工具，而不是只做展示動畫。

## 五、建議放入報告的圖表

最新版圖表來源：

`Integrated_version/docs/reports/report_benchmark_20260926T112228Z/report_assets_figfix_v2_20260927T060042Z`

| 圖表 | 建議用途 | 檔案 | 資料來源與欄位 |
|---|---|---|---|
| Figure 1 | 系統架構與驗證範圍 | `fig1_architecture_branches_v2.png` | `rtsp_summary.json`、`pipeline_summary.csv`、`orb_localization_summary.json`、`unit_test_output.txt` |
| Figure 2 | voxel、fused points、輸出大小變化 | `fig2_map_growth_split_v2.png` | `map_growth.csv`: `update_index`, `voxel_count`, `fused_points`, `output_bytes` |
| Figure 3 | prediction_long300 latency | `fig3_prediction_long300_latency_v2.png` | `map_growth.csv`、`pipeline_summary.csv`; 34 updates, mean 354.894 ms |
| Figure 4 | persistent worker 階段時間 | `fig4_persistent_grouped_latency_v2.png` | `latency_by_stage.csv`; stages 與 backend total 分開呈現 |
| Figure 5 | RSS、輸出大小與資料限制 | `fig5_memory_output_v2.png` | `memory_growth.csv`、`memory_trend_summary.json`; GPU update-aligned series 為 NOT VERIFIED |
| Figure 6 | ORB confidence/status | `fig6_orb_confidence_status_v2.png` | `orb_localization_summary.json`; 30 frame-level records |

圖說需要標示資料來源、樣本數與限制。例如 Figure 6 應註明：accepted ratio 是 confidence gate 下的接受率，不是 physical localization accuracy。

## 六、研究檢討

本專題目前最大的收穫，是把「畫面看起來能跑」和「研究上有證據支持」分開。定位接受比例只能說明多少 query 通過目前的信心門檻，不能代替 position error 或 yaw error；點雲數量增加只能說明地圖資料持續累積，不能保證新增幾何完全正確；前端能顯示 live map，也不能證明整條即時定位與導航流程都穩定。

目前定位資料多來自 `20260818` 同一段影像序列，屬於同場景或同序列測試，可能比跨場景測試容易。由於沒有獨立 ground truth，重建座標只能作為內部參考，不能當成真實世界定位真值。單眼尺度、相機參數、影像視角、RTSP 壓縮與車載振動都可能造成地圖和姿態偏差。

系統整合仍有明確缺口。Prediction replay 雖能測增量融合，但 replay 的是既有 `world_points`；persistent LingBot worker 的測試是 window-based inference，不等於每個新影格都完成真正 streaming SLAM。RTSP 方面有補充 runtime 狀態檔顯示影像、點雲與 live status 曾被串接，但正式 benchmark 中 RTSP 連線失敗，因此 RTSP 即時效能仍需標示為 `NOT VERIFIED`。

下一步應優先建立可重複的外部位置真值，再量測 position error 與 yaw error；接著在相同 mapping、query、相機內參、座標與 PnP 設定下比較定位方法。之後應進行單一長時間 RTSP 測試，完整記錄每階段延遲、丟幀、frame age、地圖更新、RAM/GPU 使用量與前端 API 回應。最後再以可控的位置與角度誤差測試 A* 路徑成功率、碰撞風險與 safety stop 行為，才能回答定位誤差如何影響導航。

## 七、專有名詞

| 專有名詞 | 白話解釋 |
|---|---|
| LingBot-MAP | 採用的開源單眼重建模型；本專題整合使用，非自行訓練 |
| ORB | 從影像找出局部特徵，再用外觀在不同影像間配對的方法 |
| PnP | 利用地圖 3D 點與影像 2D 像素的對應，反推相機位置和方向 |
| RANSAC / inlier | 反覆挑選配對估姿態並找出一致配對；inlier 是支持該姿態的配對 |
| confidence threshold | 定位結果的信心門檻；低於門檻時不把 pose 送入導航 |
| voxel | 把 3D 空間切成小格，合併同格點以控制點雲規模 |
| A* / Pure Pursuit | A* 在地圖格網找路；Pure Pursuit 依路徑前方目標計算追蹤方向 |
| dry-run | 只記錄或模擬控制命令，不實際啟用 ESP32 馬達 |

## 八、可直接放入報告的總結

整體而言，本作品目前是一套以 LingBot-MAP 為重建基礎，整合視覺重定位、增量地圖融合、前端展示與導航模擬的研究型 prototype。實驗結果顯示，在固定 `20260818` 參考地圖與同場景資料下，ORB + PnP/RANSAC 能完成 query 定位與影片 replay 定位；prediction replay 可完成 34 次 incremental map update；persistent LingBot-MAP worker 可避免每個 window 重複載入模型，fast path 也能降低 archive write 成本。

然而，本專題目前仍不能宣稱已完成真正的 online monocular SLAM 或實車閉環導航。沒有外部 ground truth 時，position error 與 yaw error 必須標示為 `NOT AVAILABLE`；acceptance rate 只能代表通過目前 confidence gate 的比例，不能代表實際定位準確率。RTSP 即時效能在正式 benchmark 中因 connection refused 而為 `NOT VERIFIED`，因此成果呈現應聚焦在系統設計、已完成的模組驗證、可追溯的 benchmark 數據，以及仍待補足的研究證據。

## 九、主要資料來源

| 資料 | 路徑 |
|---|---|
| benchmark report | `Integrated_version/docs/reports/report_benchmark_20260926T112228Z/benchmark_report.md` |
| pipeline summary | `Integrated_version/docs/reports/report_benchmark_20260926T112228Z/pipeline_summary.json` |
| ORB video replay summary | `Integrated_version/docs/reports/report_benchmark_20260926T112228Z/orb_localization_summary.json` |
| RTSP report summary | `Integrated_version/docs/reports/report_benchmark_20260926T112228Z/rtsp_summary.json` |
| 43-query ORB summary | `outputs/archive/scene_20260818_rebuild/orb_results/summary.json` |
| Figure assets v2 | `Integrated_version/docs/reports/report_benchmark_20260926T112228Z/report_assets_figfix_v2_20260927T060042Z` |
| RTSP/live mapping supplemental status | `outputs/runtime/level2_test_long/live_status.json` |
