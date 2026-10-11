# Missing Data Checklist

| Data Needed For Formal Claim | Current Status | Existing Evidence | What To Run / Collect Next |
|---|---|---|---|
| RTSP connection, frame shape, FPS, frame age | NOT VERIFIED in this report | `rtsp_summary.json` reports connection refused | Re-run bounded RTSP test and save live_status/raw logs |
| Latest-frame queue processed/dropped frames | NOT VERIFIED in this report | Prediction replay has no RTSP queue | Run live runtime with RTSP/video source and save `live_status.json` over time |
| Frontend API live map/frame/pose endpoints | NOT VERIFIED in this report | `rtsp_summary.json` marks frontend API not verified | Start web server and record `/api/live/*` responses |
| Update-aligned GPU memory | NOT VERIFIED | `memory_trend_summary.json` says GPU update-aligned series is missing | Sample GPU memory per map update in runtime records |
| Long-run memory leak conclusion | NOT VERIFIED | Only 34 updates from 43-frame prediction package | Run longer source with hundreds/thousands of updates |
| Physical position error / yaw error | NOT AVAILABLE | No external ground truth | Add motion capture, calibrated floor markers, AprilTag survey, or manually measured control points |
| Unknown-scene ORB localization package | NOT VERIFIED | Same-scene replay only | Build a new mapping package from exploration frames and test ORB against that scene |
| True online RGB monocular 3D reconstruction | NOT VERIFIED | Current LingBot path is windowed inference | Measure end-to-end camera -> inference -> fusion -> viewer with saved raw logs |
| ESP32 physical motor command | NOT VERIFIED / NOT ENABLED | Dry-run only | Keep disabled until safety review and credential cleanup |
